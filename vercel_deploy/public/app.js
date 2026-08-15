// NOVA AI Assistant Frontend Logic

// --- Configurations & States ---
const API_URL = window.location.origin; // Vercel handles routing on same origin
let chatHistory = [];
let isTTSEnabled = true;
let currentUtterance = null;
let appState = "READY"; // READY, THINKING..., SPEAKING..., LISTENING..., ERROR
let micLevel = 0.0;
let speechAmp = 0.0;
let pulsePhase = 0.0;
let rotationAngle = 0.0;

// Hologram core concentric rings definitions matching PyQt6 HoloCoreWidget exactly
const RING_DEFS = [
  { rfrac: 1.00, pw: 2.5, baseAlpha: 220, rotSpd: +6.0,  dash: null },
  { rfrac: 1.00, pw: 1.0, baseAlpha: 100, rotSpd: +6.0,  dash: null },
  { rfrac: 0.97, pw: 4.5, baseAlpha: 180, rotSpd: -4.0,  dash: [18, 8, 4, 8] },
  { rfrac: 0.92, pw: 1.2, baseAlpha: 130, rotSpd: +9.0,  dash: [6, 18] },
  { rfrac: 0.85, pw: 3.0, baseAlpha: 200, rotSpd: -5.0,  dash: [28, 10, 6, 10] },
  { rfrac: 0.80, pw: 0.8, baseAlpha: 100, rotSpd: +12.0, dash: null },
  { rfrac: 0.72, pw: 2.0, baseAlpha: 170, rotSpd: -7.0,  dash: [12, 8] },
  { rfrac: 0.65, pw: 1.0, baseAlpha: 130, rotSpd: +15.0, dash: [4, 12] },
  { rfrac: 0.58, pw: 2.5, baseAlpha: 190, rotSpd: -3.5,  dash: [20, 12, 5, 12] },
  { rfrac: 0.50, pw: 0.8, baseAlpha: 110, rotSpd: +18.0, dash: null },
  { rfrac: 0.42, pw: 1.5, baseAlpha: 150, rotSpd: -8.0,  dash: [8, 6] }
];

// State color definitions matching _STATE_COLOR
const STATE_COLORS = {
  "READY":           { r: 0,   g: 255, b: 136, hex: "#00FF88" },
  "LISTENING...":    { r: 0,   g: 255, b: 255, hex: "#00FFFF" },
  "WAKE DETECTED":   { r: 0,   g: 255, b: 255, hex: "#00FFFF" },
  "THINKING...":     { r: 255, g: 170, b: 0,   hex: "#FFAA00" },
  "EXECUTING...":    { r: 255, g: 215, b: 0,   hex: "#FFD700" },
  "SPEAKING...":     { r: 51,  g: 153, b: 255, hex: "#3399FF" },
  "ERROR":           { r: 255, g: 51,  b: 51,  hex: "#FF3333" },
  "OFFLINE":         { r: 255, g: 51,  b: 51,  hex: "#FF3333" }
};

// --- DOM References ---
const canvas = document.getElementById("holo-canvas");
const ctx = canvas.getContext("2d");
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const coreStateVal = document.getElementById("core-state-val");
const languageSelect = document.getElementById("language-select");
const ttsToggle = document.getElementById("tts-toggle");
const chatMessagesContainer = document.getElementById("chat-messages-container");
const userInput = document.getElementById("user-input");
const micBtn = document.getElementById("mic-btn");
const sendBtn = document.getElementById("send-btn");
const greetingTime = document.getElementById("greeting-time");
const networkVal = document.getElementById("network-val");

// Set initial time
if (greetingTime) {
  const now = new Date();
  greetingTime.textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

// Check network status
window.addEventListener("online", () => updateNetworkStatus(true));
window.addEventListener("offline", () => updateNetworkStatus(false));
function updateNetworkStatus(online) {
  if (networkVal) {
    if (online) {
      networkVal.textContent = "ONLINE";
      networkVal.className = "stat-value text-green";
      if (appState === "OFFLINE") setAppState("READY");
    } else {
      networkVal.textContent = "OFFLINE";
      networkVal.className = "stat-value text-red";
      setAppState("OFFLINE");
    }
  }
}

// --- App State Controls ---
function setAppState(state) {
  appState = state;
  if (statusLabel) statusLabel.textContent = state;
  if (coreStateVal) coreStateVal.textContent = state === "READY" ? "ACTIVE" : state.replace("...", "");

  // Update status dot color class
  if (statusDot) {
    statusDot.className = "status-indicator animate-pulse";
    if (state === "READY") statusDot.style.backgroundColor = STATE_COLORS["READY"].hex;
    else if (state.includes("LISTENING") || state.includes("WAKE")) statusDot.style.backgroundColor = STATE_COLORS["LISTENING..."].hex;
    else if (state.includes("THINKING") || state.includes("EXECUTING")) statusDot.style.backgroundColor = STATE_COLORS["THINKING..."].hex;
    else if (state.includes("SPEAKING")) statusDot.style.backgroundColor = STATE_COLORS["SPEAKING..."].hex;
    else statusDot.style.backgroundColor = STATE_COLORS["ERROR"].hex;
    statusDot.style.boxShadow = `0 0 10px ${statusDot.style.backgroundColor}`;
  }
}

// --- Interactive Holographic Canvas Loop ---
function drawHoloCore() {
  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  const cx = W * 0.5;
  const cy = H * 0.5;
  const baseR = Math.min(W, H) * 0.30;

  if (baseR < 10) return;

  // Increment animation angles based on current state speeds
  let speedMultiplier = 1.0;
  if (appState === "LISTENING...") speedMultiplier = 2.2;
  else if (appState === "THINKING...") speedMultiplier = 4.0;
  else if (appState === "SPEAKING...") speedMultiplier = 2.5;
  else if (appState === "ERROR" || appState === "OFFLINE") speedMultiplier = 0.6;

  rotationAngle += 0.02 * speedMultiplier;
  pulsePhase += 0.05;

  // Breathing size scaling
  let breath = 1.0 + 0.018 * Math.sin(pulsePhase);
  if (appState === "SPEAKING...") breath += speechAmp * 0.09;
  if (appState === "LISTENING...") breath += micLevel * 0.05;
  if (appState === "THINKING...") breath += 0.025 * Math.sin(Date.now() * 0.012);

  // Vibration shake displacement
  let vx = 0, vy = 0;
  if (appState === "SPEAKING...") {
    vx = (Math.random() - 0.5) * speechAmp * 15;
    vy = (Math.random() - 0.5) * speechAmp * 15;
  } else if (appState === "LISTENING...") {
    vx = (Math.random() - 0.5) * micLevel * 8;
    vy = (Math.random() - 0.5) * micLevel * 8;
  }
  const hx = cx + vx;
  const hy = cy + vy;

  const activeColor = STATE_COLORS[appState] || STATE_COLORS["READY"];

  // 1. SOFT OUTER GLOW
  const glowR = baseR * 1.55 * breath;
  let glowPeak = 0.2;
  if (appState === "SPEAKING...") glowPeak = 0.3 + speechAmp * 0.25;
  else if (appState === "LISTENING...") glowPeak = 0.25 + micLevel * 0.2;
  else if (appState === "THINKING...") glowPeak = 0.22;

  const radialGlow = ctx.createRadialGradient(hx, hy, 0, hx, hy, glowR);
  radialGlow.addColorStop(0.0, `rgba(${activeColor.r}, ${activeColor.g}, ${activeColor.b}, ${glowPeak})`);
  radialGlow.addColorStop(0.45, `rgba(${activeColor.r}, ${activeColor.g}, ${activeColor.b}, ${glowPeak * 0.5})`);
  radialGlow.addColorStop(1.0, `rgba(${activeColor.r}, ${activeColor.g}, ${activeColor.b}, 0)`);
  
  ctx.beginPath();
  ctx.arc(hx, hy, glowR, 0, Math.PI * 2);
  ctx.fillStyle = radialGlow;
  ctx.fill();

  // 2. HUD CONCENTRIC RINGS
  ctx.globalCompositeOperation = "screen";

  RING_DEFS.forEach((ring) => {
    const ringR = baseR * ring.rfrac * breath;
    const aBoost = appState === "SPEAKING..." ? speechAmp * 80 :
                   appState === "LISTENING..." ? micLevel * 50 :
                   appState === "THINKING..." ? 30 : 0;
    const alpha = Math.min(255, ring.baseAlpha + aBoost) / 255;
    const ringAngle = rotationAngle * ring.rotSpd * 0.2;

    ctx.save();
    ctx.translate(hx, hy);
    ctx.rotate(ringAngle);

    ctx.beginPath();
    ctx.arc(0, 0, ringR, 0, Math.PI * 2);
    ctx.lineWidth = ring.pw;
    ctx.strokeStyle = `rgba(${activeColor.r}, ${activeColor.g}, ${activeColor.b}, ${alpha * 0.8})`;

    if (ring.dash) {
      ctx.setLineDash(ring.dash);
    } else {
      ctx.setLineDash([]);
    }

    ctx.stroke();
    ctx.restore();
  });

  ctx.globalCompositeOperation = "source-over";

  // Simulate speaking amplitude decay
  if (appState === "SPEAKING...") {
    speechAmp = Math.max(0.02, speechAmp - 0.05);
  } else {
    speechAmp = 0;
  }

  requestAnimationFrame(drawHoloCore);
}

// Start rendering
drawHoloCore();

// --- Speech Synthesis (Text-To-Speech) ---
function speakResponse(text, langCode) {
  if (!isTTSEnabled || !('speechSynthesis' in window)) return;

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  currentUtterance = new SpeechSynthesisUtterance(text);
  
  // Set voice language
  currentUtterance.lang = langCode || "en-US";
  if (langCode === "te") currentUtterance.lang = "te-IN";
  else if (langCode === "hi") currentUtterance.lang = "hi-IN";
  else if (langCode === "ta") currentUtterance.lang = "ta-IN";
  else if (langCode === "kn") currentUtterance.lang = "kn-IN";

  // Attempt to select a high-quality localized voice
  const voices = window.speechSynthesis.getVoices();
  let matchedVoice = null;
  
  // Match matching language code exactly
  for (let v of voices) {
    if (v.lang.toLowerCase().includes(currentUtterance.lang.toLowerCase())) {
      matchedVoice = v;
      if (v.name.includes("Google") || v.name.includes("Natural")) {
        break; // Prefer google or natural sounding web voices
      }
    }
  }
  if (matchedVoice) currentUtterance.voice = matchedVoice;

  currentUtterance.rate = 1.0;
  currentUtterance.volume = 1.0;

  // Visual voice synchronization using speech amp simulation
  currentUtterance.onstart = () => {
    setAppState("SPEAKING...");
    speechAmp = 0.8;
  };

  currentUtterance.onboundary = (event) => {
    if (event.name === "word") {
      speechAmp = 0.5 + Math.random() * 0.5; // Simulate voice reactive jump
    }
  };

  currentUtterance.onend = () => {
    setAppState("READY");
    speechAmp = 0;
  };

  currentUtterance.onerror = () => {
    setAppState("READY");
    speechAmp = 0;
  };

  window.speechSynthesis.speak(currentUtterance);
}

// Ensure voices are loaded
if ('speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

// --- Speech Recognition (Speech-To-Text) ---
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRec();
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    setAppState("LISTENING...");
    if (micBtn) micBtn.classList.add("listening");
    micLevel = 0.6;
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (userInput) {
      userInput.value = transcript;
    }
    micLevel = 0;
    // Auto-send voice queries
    sendMessage();
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    setAppState("READY");
    if (micBtn) micBtn.classList.remove("listening");
    micLevel = 0;
  };

  recognition.onend = () => {
    if (appState === "LISTENING...") {
      setAppState("READY");
    }
    if (micBtn) micBtn.classList.remove("listening");
    micLevel = 0;
  };
}

function toggleVoiceRecognition() {
  if (!recognition) {
    alert("Speech recognition is not supported in this browser. Please use Chrome, Safari or Edge.");
    return;
  }

  if (appState === "LISTENING...") {
    recognition.stop();
  } else {
    // Stop any active speech output
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    
    // Set appropriate language for recognition
    const lang = languageSelect.value;
    if (lang === "te") recognition.lang = "te-IN";
    else if (lang === "hi") recognition.lang = "hi-IN";
    else if (lang === "ta") recognition.lang = "ta-IN";
    else if (lang === "kn") recognition.lang = "kn-IN";
    else recognition.lang = "en-US";

    recognition.start();
  }
}

// --- Communications & API Integration ---
async function sendMessage() {
  if (appState === "THINKING...") return;

  const query = userInput.value.trim();
  if (!query) return;

  // Clear input
  userInput.value = "";

  // Append user message bubble
  appendMessage("user", query);
  setAppState("THINKING...");

  // Add loading bubble indicator
  const loadingId = appendLoadingIndicator();

  // Prepare payload
  const currentLang = languageSelect.value;
  const payload = {
    message: query,
    history: chatHistory.slice(-10), // Send last 10 turns as history context
    language: currentLang
  };

  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    });

    const data = await res.json();
    removeLoadingIndicator(loadingId);

    if (res.ok && data.response) {
      appendMessage("assistant", data.response);
      setAppState("READY");
      
      // Update local context history
      chatHistory.push({ role: "user", content: query });
      chatHistory.push({ role: "assistant", content: data.response });

      // Speak response out loud
      speakResponse(data.response, currentLang);
    } else {
      const errMsg = data.error || "Failed to communicate with NOVA brain.";
      appendMessage("assistant", `ERROR: ${errMsg}`);
      setAppState("ERROR");
    }

  } catch (err) {
    console.error("API error:", err);
    removeLoadingIndicator(loadingId);
    appendMessage("assistant", "CRITICAL ERROR: Connection to server backend refused.");
    setAppState("ERROR");
  }
}

// Helper: Append Message Bubble to Feed
function appendMessage(role, text) {
  const msgDiv = document.createElement("div");
  msgDiv.className = `message ${role === "user" ? "user-msg" : "assistant-msg"}`;

  const bubbleDiv = document.createElement("div");
  bubbleDiv.className = "msg-bubble";

  const p = document.createElement("p");
  // Simple paragraph styling (supports multiline text)
  p.innerHTML = text.replace(/\n/g, "<br>");
  bubbleDiv.appendChild(p);

  const timeSpan = document.createElement("span");
  timeSpan.className = "msg-time";
  const now = new Date();
  timeSpan.textContent = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
  bubbleDiv.appendChild(timeSpan);

  msgDiv.appendChild(bubbleDiv);
  chatMessagesContainer.appendChild(msgDiv);
  
  // Auto-scroll
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

// Helper: Append Loading Spin Indicator
function appendLoadingIndicator() {
  const id = "loading-" + Date.now();
  const msgDiv = document.createElement("div");
  msgDiv.className = "message assistant-msg";
  msgDiv.id = id;

  const bubbleDiv = document.createElement("div");
  bubbleDiv.className = "msg-bubble";

  const container = document.createElement("div");
  container.className = "spinner-container";
  container.innerHTML = '<span>NOVA is thinking</span><div class="loading-dots"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div>';
  
  bubbleDiv.appendChild(container);
  msgDiv.appendChild(bubbleDiv);
  chatMessagesContainer.appendChild(msgDiv);
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
  return id;
}

function removeLoadingIndicator(id) {
  const indicator = document.getElementById(id);
  if (indicator) indicator.remove();
}

// --- Event Listeners ---
sendBtn.addEventListener("click", sendMessage);
userInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendMessage();
});

micBtn.addEventListener("click", toggleVoiceRecognition);

ttsToggle.addEventListener("click", () => {
  isTTSEnabled = !isTTSEnabled;
  if (isTTSEnabled) {
    ttsToggle.classList.add("active");
  } else {
    ttsToggle.classList.remove("active");
    // Cancel if currently speaking
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (appState === "SPEAKING...") setAppState("READY");
  }
});

// Setup initial status
setAppState("READY");
updateNetworkStatus(navigator.onLine);
