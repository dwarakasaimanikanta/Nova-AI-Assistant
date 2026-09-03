/**
 * NOVA AI Assistant — Frontend Application v2.1
 *
 * Modern ChatGPT-style interface with:
 * - Persistent chat history (localStorage)
 * - File & image upload with client-side extraction
 * - Markdown rendering with code highlighting
 * - Dark/light theme
 * - Mobile-responsive sidebar
 * - Voice input/output (preserved from v1)
 * - AUTO / WEB / AI answer mode selector (v2.1)
 * - Real-time web search via Google Search grounding (v2.1)
 * - Sources panel for web-grounded answers (v2.1)
 * - Share button on every response (v2.1)
 */

// ============================================================
// CONFIGURATION & CONSTANTS
// ============================================================
const API_URL = window.location.origin;
const MAX_IMAGE_SIZE = 10 * 1024 * 1024;  // 10MB
const MAX_FILE_SIZE = 5 * 1024 * 1024;    // 5MB
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const ALLOWED_FILE_TYPES = ['.pdf', '.txt', '.docx', '.doc', '.md', '.csv', '.json'];

// ============================================================
// STORAGE MANAGER — Persistent localStorage wrapper
// ============================================================
class StorageManager {
  constructor() {
    this.userId = null;
    this.CONVERSATIONS_KEY = 'nova_conversations';
    this.PREFERENCES_KEY = 'nova_preferences';
    this.PLAN_KEY = 'nova_plan_data';
  }

  setUser(userId) {
    this.userId = userId || null;
    this.CONVERSATIONS_KEY = userId ? `nova_conversations_${userId}` : 'nova_conversations_guest';
    this.PREFERENCES_KEY = userId ? `nova_preferences_${userId}` : 'nova_preferences';
  }

  // ---- Conversations ----
  getAllConversations() {
    try {
      const data = localStorage.getItem(this.CONVERSATIONS_KEY);
      return data ? JSON.parse(data) : [];
    } catch {
      return [];
    }
  }

  saveAllConversations(conversations) {
    try {
      localStorage.setItem(this.CONVERSATIONS_KEY, JSON.stringify(conversations));
    } catch (e) {
      console.warn('Storage full, removing oldest conversations...', e);
      // If storage is full, remove oldest non-pinned conversations
      const sorted = conversations
        .filter(c => !c.pinned)
        .sort((a, b) => new Date(a.updatedAt) - new Date(b.updatedAt));
      if (sorted.length > 0) {
        const toRemove = sorted[0].id;
        conversations = conversations.filter(c => c.id !== toRemove);
        this.saveAllConversations(conversations);
      }
    }
  }

  getConversation(id) {
    const all = this.getAllConversations();
    return all.find(c => c.id === id) || null;
  }

  saveConversation(conversation) {
    const all = this.getAllConversations();
    const idx = all.findIndex(c => c.id === conversation.id);
    if (idx >= 0) {
      all[idx] = conversation;
    } else {
      all.unshift(conversation);
    }
    this.saveAllConversations(all);
  }

  deleteConversation(id) {
    const all = this.getAllConversations().filter(c => c.id !== id);
    this.saveAllConversations(all);
  }

  // ---- Preferences ----
  getPreferences() {
    try {
      const data = localStorage.getItem(this.PREFERENCES_KEY);
      return data ? JSON.parse(data) : this.defaultPreferences();
    } catch {
      return this.defaultPreferences();
    }
  }

  savePreferences(prefs) {
    localStorage.setItem(this.PREFERENCES_KEY, JSON.stringify(prefs));
  }

  defaultPreferences() {
    return {
      theme: 'dark',
      language: 'en',
      ttsEnabled: true,
      lastConversationId: null
    };
  }

  // ---- Plan / Monetization ----
  getPlanData() {
    try {
      const data = localStorage.getItem(this.PLAN_KEY);
      return data ? JSON.parse(data) : this.defaultPlanData();
    } catch {
      return this.defaultPlanData();
    }
  }

  savePlanData(planData) {
    localStorage.setItem(this.PLAN_KEY, JSON.stringify(planData));
  }

  defaultPlanData() {
    return {
      plan: 'free',
      dailyRequestCount: 0,
      lastRequestDate: new Date().toDateString(),
      totalRequests: 0
    };
  }
}

// ============================================================
// PLAN MANAGER — Monetization architecture preparation
// ============================================================
class PlanManager {
  constructor(storage) {
    this.storage = storage;
    this.plans = {
      free: {
        name: 'Free',
        dailyLimit: 50,    // Daily request limit
        maxHistory: 50,     // Max saved conversations
        features: ['basic_chat', 'voice_input', 'voice_output']
      },
      premium: {
        name: 'Premium',
        dailyLimit: Infinity,
        maxHistory: Infinity,
        features: ['basic_chat', 'voice_input', 'voice_output', 'image_upload',
                   'file_upload', 'priority_responses', 'unlimited_history']
      }
    };
  }

  canSendMessage() {
    // Currently always returns true — limits not enforced yet
    // When monetization is enabled, uncomment the logic below:
    /*
    const planData = this.storage.getPlanData();
    const plan = this.plans[planData.plan] || this.plans.free;
    
    // Reset daily count if new day
    if (planData.lastRequestDate !== new Date().toDateString()) {
      planData.dailyRequestCount = 0;
      planData.lastRequestDate = new Date().toDateString();
      this.storage.savePlanData(planData);
    }
    
    return planData.dailyRequestCount < plan.dailyLimit;
    */
    return true;
  }

  trackRequest() {
    const planData = this.storage.getPlanData();
    if (planData.lastRequestDate !== new Date().toDateString()) {
      planData.dailyRequestCount = 0;
      planData.lastRequestDate = new Date().toDateString();
    }
    planData.dailyRequestCount++;
    planData.totalRequests++;
    this.storage.savePlanData(planData);
  }

  getCurrentPlan() {
    const planData = this.storage.getPlanData();
    return this.plans[planData.plan] || this.plans.free;
  }
}

// ============================================================
// THEME MANAGER
// ============================================================
class ThemeManager {
  constructor(storage) {
    this.storage = storage;
    this.init();
  }

  init() {
    const prefs = this.storage.getPreferences();
    let theme = prefs.theme;
    
    // If no saved preference, detect system preference
    if (!theme) {
      theme = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
    }
    
    this.applyTheme(theme, false);
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
      if (!this.storage.getPreferences().theme) {
        this.applyTheme(e.matches ? 'dark' : 'light', true);
      }
    });
  }

  toggle() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    this.applyTheme(next, true);
    return next;
  }

  applyTheme(theme, animate) {
    if (animate) {
      document.body.classList.add('theme-transitioning');
      setTimeout(() => document.body.classList.remove('theme-transitioning'), 350);
    }
    
    document.documentElement.setAttribute('data-theme', theme);
    
    // Update meta theme-color for mobile browsers
    const metaTheme = document.querySelector('meta[name="theme-color"]');
    if (metaTheme) {
      metaTheme.content = theme === 'dark' ? '#0a0f1e' : '#f7f8fc';
    }

    // Update highlight.js theme
    const hljsLink = document.getElementById('hljs-theme');
    if (hljsLink) {
      hljsLink.href = theme === 'dark'
        ? 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-dark.min.css'
        : 'https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/atom-one-light.min.css';
    }
    
    // Toggle theme icons
    const darkIcon = document.querySelector('.theme-icon-dark');
    const lightIcon = document.querySelector('.theme-icon-light');
    if (darkIcon && lightIcon) {
      darkIcon.style.display = theme === 'dark' ? 'block' : 'none';
      lightIcon.style.display = theme === 'light' ? 'block' : 'none';
    }
    
    // Save preference
    const prefs = this.storage.getPreferences();
    prefs.theme = theme;
    this.storage.savePreferences(prefs);
  }
}

// ============================================================
// FILE UPLOAD MANAGER
// ============================================================
class FileUploadManager {
  constructor() {
    this.pendingImage = null;    // { file, dataUrl, base64, mime }
    this.pendingFile = null;     // { file, name, text }
  }

  clear() {
    this.pendingImage = null;
    this.pendingFile = null;
    this.updatePreviewUI();
  }

  async handleImageSelect(file) {
    if (!file) return;

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      showToast('Unsupported image format. Please use JPEG, PNG, GIF, or WebP.', 'error');
      return;
    }

    if (file.size > MAX_IMAGE_SIZE) {
      showToast('Image is too large. Maximum size is 10MB.', 'error');
      return;
    }

    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const dataUrl = e.target.result;
        // Extract base64 data (remove the data:image/xxx;base64, prefix)
        const base64 = dataUrl.split(',')[1];
        this.pendingImage = {
          file: file,
          dataUrl: dataUrl,
          base64: base64,
          mime: file.type
        };
        this.pendingFile = null; // Only one attachment at a time
        this.updatePreviewUI();
        resolve(this.pendingImage);
      };
      reader.onerror = () => {
        showToast('Failed to read the image file.', 'error');
        resolve(null);
      };
      reader.readAsDataURL(file);
    });
  }

  async handleFileSelect(file) {
    if (!file) return;

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ALLOWED_FILE_TYPES.includes(ext)) {
      showToast(`Unsupported file type: ${ext}. Supported: PDF, TXT, DOCX, MD, CSV, JSON.`, 'error');
      return;
    }

    if (file.size > MAX_FILE_SIZE) {
      showToast('File is too large. Maximum size is 5MB.', 'error');
      return;
    }

    try {
      let text = '';
      
      if (ext === '.pdf') {
        text = await this.extractPdfText(file);
      } else if (ext === '.docx' || ext === '.doc') {
        text = await this.extractDocxText(file);
      } else {
        // TXT, MD, CSV, JSON — read as plain text
        text = await this.readAsText(file);
      }

      if (!text || text.trim().length === 0) {
        showToast('Could not extract text from the file. The file may be empty or protected.', 'error');
        return;
      }

      this.pendingFile = {
        file: file,
        name: file.name,
        text: text.substring(0, 20000) // Limit to 20k chars
      };
      this.pendingImage = null; // Only one attachment at a time
      this.updatePreviewUI();
      showToast(`File "${file.name}" loaded successfully.`, 'success');

    } catch (err) {
      console.error('File extraction error:', err);
      showToast('Failed to process the file. Please try a different file.', 'error');
    }
  }

  readAsText(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = reject;
      reader.readAsText(file);
    });
  }

  async extractPdfText(file) {
    if (!window.pdfjsLib) {
      showToast('PDF processing library not loaded. Please refresh and try again.', 'error');
      return '';
    }
    
    const arrayBuffer = await file.arrayBuffer();
    window.pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    
    const pdf = await window.pdfjsLib.getDocument({ data: arrayBuffer }).promise;
    let fullText = '';
    
    for (let i = 1; i <= Math.min(pdf.numPages, 50); i++) { // Max 50 pages
      const page = await pdf.getPage(i);
      const textContent = await page.getTextContent();
      const pageText = textContent.items.map(item => item.str).join(' ');
      fullText += pageText + '\n';
    }
    
    return fullText;
  }

  async extractDocxText(file) {
    if (!window.mammoth) {
      showToast('DOCX processing library not loaded. Please refresh and try again.', 'error');
      return '';
    }
    
    const arrayBuffer = await file.arrayBuffer();
    const result = await window.mammoth.extractRawText({ arrayBuffer: arrayBuffer });
    return result.value;
  }

  updatePreviewUI() {
    const previewArea = document.getElementById('attachment-preview');
    const itemsContainer = document.getElementById('attachment-items');
    
    if (!previewArea || !itemsContainer) return;
    
    itemsContainer.innerHTML = '';
    
    if (this.pendingImage) {
      previewArea.style.display = 'block';
      const chip = document.createElement('div');
      chip.className = 'attachment-chip';
      chip.innerHTML = `
        <img src="${this.pendingImage.dataUrl}" alt="Upload preview">
        <span class="attachment-chip-name">${this.pendingImage.file?.name || 'Image'}</span>
        <button class="attachment-remove-btn" title="Remove">&times;</button>
      `;
      chip.querySelector('.attachment-remove-btn').addEventListener('click', () => {
        this.pendingImage = null;
        this.updatePreviewUI();
        updateSendButtonState();
      });
      itemsContainer.appendChild(chip);
    } else if (this.pendingFile) {
      previewArea.style.display = 'block';
      const chip = document.createElement('div');
      chip.className = 'attachment-chip';
      chip.innerHTML = `
        <svg class="file-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        <span class="attachment-chip-name">${this.pendingFile.name}</span>
        <button class="attachment-remove-btn" title="Remove">&times;</button>
      `;
      chip.querySelector('.attachment-remove-btn').addEventListener('click', () => {
        this.pendingFile = null;
        this.updatePreviewUI();
        updateSendButtonState();
      });
      itemsContainer.appendChild(chip);
    } else {
      previewArea.style.display = 'none';
    }
  }

  hasPending() {
    return !!(this.pendingImage || this.pendingFile);
  }
}

// ============================================================
// MARKDOWN RENDERER
// ============================================================
function renderMarkdown(text) {
  if (!text) return '';

  // Configure marked
  if (window.marked) {
    const renderer = new marked.Renderer();
    
    // Custom code block rendering with copy button
    renderer.code = function(code, language) {
      const lang = language || 'plaintext';
      let highlighted;
      try {
        if (window.hljs && language && hljs.getLanguage(language)) {
          highlighted = hljs.highlight(code, { language: language }).value;
        } else {
          highlighted = escapeHtml(code);
        }
      } catch {
        highlighted = escapeHtml(code);
      }

      return `<div class="code-block-wrapper">
        <div class="code-block-header">
          <span>${lang}</span>
          <button class="code-copy-btn" onclick="copyCodeBlock(this)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
            </svg>
            <span>Copy</span>
          </button>
        </div>
        <pre><code class="hljs language-${lang}">${highlighted}</code></pre>
      </div>`;
    };

    marked.setOptions({
      renderer: renderer,
      breaks: true,
      gfm: true
    });

    return marked.parse(text);
  }

  // Fallback: basic formatting if marked isn't loaded
  return text.replace(/\n/g, '<br>');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Global function for code copy buttons
function copyCodeBlock(btn) {
  const codeEl = btn.closest('.code-block-wrapper').querySelector('code');
  const text = codeEl.textContent;
  navigator.clipboard.writeText(text).then(() => {
    const span = btn.querySelector('span');
    span.textContent = 'Copied!';
    setTimeout(() => { span.textContent = 'Copy'; }, 2000);
  }).catch(() => {
    showToast('Failed to copy code.', 'error');
  });
}

// ============================================================
// TOAST NOTIFICATIONS
// ============================================================
function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  if (!container) return;
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  
  setTimeout(() => {
    toast.style.animation = 'toastSlideOut 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ============================================================
// CONFIRMATION MODAL
// ============================================================
function showModal(title, message, onConfirm) {
  const overlay = document.getElementById('modal-overlay');
  const titleEl = document.getElementById('modal-title');
  const msgEl = document.getElementById('modal-message');
  const confirmBtn = document.getElementById('modal-confirm-btn');
  const cancelBtn = document.getElementById('modal-cancel-btn');
  const iconEl = document.getElementById('modal-icon');

  if (!overlay) return;

  titleEl.textContent = title;
  msgEl.textContent = message;
  iconEl.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
  </svg>`;
  overlay.style.display = 'flex';

  const cleanup = () => {
    overlay.style.display = 'none';
    confirmBtn.removeEventListener('click', handleConfirm);
    cancelBtn.removeEventListener('click', cleanup);
    overlay.removeEventListener('click', handleOverlayClick);
  };

  const handleConfirm = () => {
    cleanup();
    if (onConfirm) onConfirm();
  };

  const handleOverlayClick = (e) => {
    if (e.target === overlay) cleanup();
  };

  confirmBtn.addEventListener('click', handleConfirm);
  cancelBtn.addEventListener('click', cleanup);
  overlay.addEventListener('click', handleOverlayClick);
}


// ============================================================
// APPLICATION STATE
// ============================================================
const storage = new StorageManager();
const planManager = new PlanManager(storage);
const themeManager = new ThemeManager(storage);
const fileUploadManager = new FileUploadManager();

let currentConversationId = null;
let appState = 'READY';
let isTTSEnabled = true;
let currentUtterance = null;

// ---- DOM References ----
const sidebar = document.getElementById('sidebar');
const sidebarOverlay = document.getElementById('sidebar-overlay');
const sidebarCloseBtn = document.getElementById('sidebar-close-btn');
const hamburgerBtn = document.getElementById('hamburger-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const searchInput = document.getElementById('search-chats');
const pinnedChatList = document.getElementById('pinned-chat-list');
const recentChatList = document.getElementById('recent-chat-list');
const pinnedSection = document.getElementById('pinned-section');
const chatContainer = document.getElementById('chat-container');
const messagesList = document.getElementById('messages-list');
const welcomeScreen = document.getElementById('welcome-screen');
const chatTitleEl = document.getElementById('current-chat-title');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const ttsToggle = document.getElementById('tts-toggle');
const languageSelect = document.getElementById('language-select');
const imageUploadBtn = document.getElementById('image-upload-btn');
const imageInput = document.getElementById('image-input');
const fileUploadBtn = document.getElementById('file-upload-btn');
const fileInput = document.getElementById('file-input');
const themeToggleBtn = document.getElementById('theme-toggle-btn');
const statusDot = document.getElementById('status-dot');
const statusLabel = document.getElementById('status-label');
const statusBadge = document.getElementById('status-badge');
const modeButtons = document.querySelectorAll('.mode-btn');

// ── Answer-mode state (auto | web | ai) ────────────────────────────────────
let currentSearchMode = 'auto';

modeButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    modeButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentSearchMode = btn.dataset.mode;
  });
});

// ============================================================
// APP STATE MANAGEMENT
// ============================================================
function setAppState(state) {
  appState = state;
  if (statusLabel) statusLabel.textContent = state;
  
  const colors = {
    'READY': { color: 'var(--accent-green)', bg: 'var(--accent-green-dim)' },
    'LISTENING...': { color: 'var(--accent-cyan)', bg: 'var(--accent-cyan-dim)' },
    'THINKING...': { color: 'var(--accent-amber)', bg: 'rgba(255,170,0,0.1)' },
    'SPEAKING...': { color: '#3399ff', bg: 'rgba(51,153,255,0.1)' },
    'ERROR': { color: 'var(--accent-red)', bg: 'rgba(255,71,87,0.1)' },
    'OFFLINE': { color: 'var(--accent-red)', bg: 'rgba(255,71,87,0.1)' }
  };

  const c = colors[state] || colors['READY'];
  
  if (statusDot) {
    statusDot.style.background = c.color;
    statusDot.style.color = c.color;
  }
  if (statusBadge) {
    statusBadge.style.borderColor = c.color;
    statusBadge.style.background = c.bg;
    statusBadge.style.color = c.color;
  }
}

// Network status
window.addEventListener('online', () => {
  if (appState === 'OFFLINE') setAppState('READY');
  showToast('Connection restored.', 'success');
});
window.addEventListener('offline', () => {
  setAppState('OFFLINE');
  showToast('You are offline. Messages cannot be sent.', 'error');
});

// ============================================================
// SIDEBAR MANAGEMENT
// ============================================================
function openSidebar() {
  sidebar.classList.add('open');
  sidebarOverlay.classList.add('show');
  document.body.style.overflow = 'hidden';
}

function closeSidebar() {
  sidebar.classList.remove('open');
  sidebarOverlay.classList.remove('show');
  document.body.style.overflow = '';
}

hamburgerBtn.addEventListener('click', openSidebar);
sidebarCloseBtn.addEventListener('click', closeSidebar);
sidebarOverlay.addEventListener('click', closeSidebar);

// ============================================================
// CHAT HISTORY RENDERING
// ============================================================
function renderChatLists(filter = '') {
  const conversations = storage.getAllConversations();
  const pinned = conversations.filter(c => c.pinned);
  const recent = conversations.filter(c => !c.pinned);

  // Apply search filter
  const filterLower = filter.toLowerCase();
  const filteredPinned = filter
    ? pinned.filter(c => c.title.toLowerCase().includes(filterLower))
    : pinned;
  const filteredRecent = filter
    ? recent.filter(c => c.title.toLowerCase().includes(filterLower))
    : recent;

  // Pinned section
  pinnedSection.style.display = filteredPinned.length > 0 ? 'block' : 'none';
  pinnedChatList.innerHTML = '';
  filteredPinned.forEach(c => pinnedChatList.appendChild(createChatItem(c)));

  // Recent section
  recentChatList.innerHTML = '';
  if (filteredRecent.length === 0 && filteredPinned.length === 0) {
    recentChatList.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-tertiary);font-size:0.8rem;">
      No conversations yet. Start a new chat!
    </div>`;
  } else {
    filteredRecent.forEach(c => recentChatList.appendChild(createChatItem(c)));
  }
}

function createChatItem(conversation) {
  const div = document.createElement('div');
  div.className = `chat-item${conversation.id === currentConversationId ? ' active' : ''}`;
  div.dataset.id = conversation.id;

  div.innerHTML = `
    <svg class="chat-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
    </svg>
    <span class="chat-item-title">${escapeHtml(conversation.title)}</span>
    <div class="chat-item-actions">
      <button class="chat-action-btn pin-btn ${conversation.pinned ? 'pin-active' : ''}" title="${conversation.pinned ? 'Unpin' : 'Pin'}">
        <svg viewBox="0 0 24 24" fill="${conversation.pinned ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
          <path d="M12 2l1.5 5.5L19 9l-4 3.5L16.5 18 12 15l-4.5 3 1.5-5.5L5 9l5.5-1.5z"/>
        </svg>
      </button>
      <button class="chat-action-btn rename-btn" title="Rename">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
          <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
        </svg>
      </button>
      <button class="chat-action-btn delete-btn" title="Delete">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
        </svg>
      </button>
    </div>
  `;

  // Click to load conversation
  div.addEventListener('click', (e) => {
    if (e.target.closest('.chat-action-btn')) return;
    loadConversation(conversation.id);
    closeSidebar();
  });

  // Pin/Unpin
  div.querySelector('.pin-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    togglePinChat(conversation.id);
  });

  // Rename
  div.querySelector('.rename-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    startRenameChat(div, conversation.id);
  });

  // Delete
  div.querySelector('.delete-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    deleteChat(conversation.id, conversation.title);
  });

  return div;
}

function togglePinChat(id) {
  const conv = storage.getConversation(id);
  if (!conv) return;
  conv.pinned = !conv.pinned;
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  renderChatLists(searchInput.value);
  showToast(conv.pinned ? 'Chat pinned.' : 'Chat unpinned.', 'info');
}

function startRenameChat(itemEl, id) {
  const titleEl = itemEl.querySelector('.chat-item-title');
  const currentTitle = titleEl.textContent;
  
  const input = document.createElement('input');
  input.type = 'text';
  input.className = 'chat-item-rename-input';
  input.value = currentTitle;
  
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  const finishRename = () => {
    const newTitle = input.value.trim() || currentTitle;
    const conv = storage.getConversation(id);
    if (conv) {
      conv.title = newTitle;
      storage.saveConversation(conv);
      if (id === currentConversationId) {
        chatTitleEl.textContent = newTitle;
      }
    }
    renderChatLists(searchInput.value);
  };

  input.addEventListener('blur', finishRename);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
  });
}

function deleteChat(id, title) {
  showModal(
    'Delete Conversation',
    `Are you sure you want to delete "${title}"? This action cannot be undone.`,
    () => {
      storage.deleteConversation(id);
      if (id === currentConversationId) {
        startNewChat();
      }
      renderChatLists(searchInput.value);
      showToast('Conversation deleted.', 'info');
    }
  );
}

// Search
searchInput.addEventListener('input', () => {
  renderChatLists(searchInput.value);
});

// ============================================================
// CONVERSATION MANAGEMENT
// ============================================================
function generateId() {
  return 'conv_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
}

function generateTitle(firstMessage) {
  // Generate a short title from the first user message
  const clean = firstMessage.replace(/[\n\r]+/g, ' ').trim();
  if (clean.length <= 40) return clean;
  return clean.substring(0, 37) + '...';
}

function createNewConversation() {
  const id = generateId();
  const conversation = {
    id: id,
    title: 'New Chat',
    messages: [],
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    pinned: false
  };
  return conversation;
}

function startNewChat() {
  const conv = createNewConversation();
  currentConversationId = conv.id;
  // Don't save until first message
  
  // Clear UI
  messagesList.innerHTML = '';
  welcomeScreen.style.display = 'flex';
  chatTitleEl.textContent = 'New Chat';
  fileUploadManager.clear();
  
  // Update sidebar
  renderChatLists(searchInput.value);
  
  // Save preference
  const prefs = storage.getPreferences();
  prefs.lastConversationId = conv.id;
  storage.savePreferences(prefs);

  // Focus input
  userInput.focus();
}

function loadConversation(id) {
  const conv = storage.getConversation(id);
  if (!conv) {
    showToast('Conversation not found.', 'error');
    return;
  }

  currentConversationId = conv.id;
  chatTitleEl.textContent = conv.title;
  fileUploadManager.clear();

  // Render messages
  messagesList.innerHTML = '';
  welcomeScreen.style.display = conv.messages.length === 0 ? 'flex' : 'none';

  conv.messages.forEach(msg => {
    if (msg.type === 'web_images' && msg.images) {
      appendWebImagesToDOM(
        msg.query || msg.content,
        msg.images,
        msg.provider || 'Web Search',
        msg.timestamp
      );
    } else if (msg.type === 'image_generated' && (msg.image_url || msg.image_b64 || msg.display_src)) {
      appendGeneratedImageToDOM(
        msg.image_prompt || msg.content,
        msg.image_url || msg.display_src,
        msg.provider || 'Image',
        msg.timestamp,
        msg.image_prompt
      );
    } else {
      appendMessageToDOM(
        msg.role,
        msg.content,
        msg.timestamp,
        msg.image,
        msg.fileName,
        msg.web_search_used || false,
        msg.sources || [],
        msg.web_search_fallback || false
      );
    }
  });

  // Scroll to bottom
  chatContainer.scrollTop = chatContainer.scrollHeight;

  // Update sidebar active state
  renderChatLists(searchInput.value);

  // Save preference
  const prefs = storage.getPreferences();
  prefs.lastConversationId = id;
  storage.savePreferences(prefs);
}

function getCurrentConversation() {
  if (!currentConversationId) return null;
  let conv = storage.getConversation(currentConversationId);
  if (!conv) {
    // Create new conversation object if not saved yet
    conv = createNewConversation();
    conv.id = currentConversationId;
  }
  return conv;
}


// ============================================================
// IMAGE INTENT CLASSIFIER
// ============================================================

/**
 * Returns true ONLY if the user is explicitly requesting AI image GENERATION / ARTWORK.
 * e.g. "generate an AI image of waterfalls", "create AI artwork", "make a fantasy image of a castle",
 *      "waterfalls AI image generate cheyyi", "generate an AI image of a futuristic robot"
 */
function isExplicitAIImageRequest(text) {
  if (!text || text.trim().length < 3) return false;
  const raw = text.trim();
  const lower = raw.toLowerCase();
  const compact = lower.replace(/[^a-z0-9]/g, '');

  // Guard: If it's a document/pdf request (e.g. 'generate this image into pdf', 'make a pdf'), do not treat as AI image generation
  if (/\b(?:pdf|docx|word\s+document|document|roadmap|resume|cv)\b/i.test(lower)) {
    return false;
  }

  const explicitAIPatterns = [
    // 1. Generation verbs (generate, create, make, draw, render, paint, design) + visual nouns anywhere in sentence
    /\b(?:generate|create|make|draw|render|paint|design)\b.*?\b(?:image|photo|picture|pic|artwork|painting|art|avatar|poster|wallpaper|illustration)s?\b/i,
    
    // 2. Visual nouns + generation verbs anywhere (e.g. 'robot image generate', 'photo create', 'wallpaper make')
    /\b(?:image|photo|picture|pic|artwork|painting|art|avatar|poster|wallpaper|illustration)s?\b.*?\b(?:generate|create|make|draw|render|paint|design)\b/i,
    
    // 3. Direct visual creation actions without noun (e.g. 'draw a dragon', 'render a cyberpunk city', 'paint a sunset')
    /^\s*(?:draw|render|paint|illustrate|design)\s+(?:a\s+|an\s+|the\s+)?[\w\s]{2,}/i,
    
    // 4. Explicit 'generate/create a/an ...' prompts
    /^\s*(?:generate|create|make)\s+(?:a\s+|an\s+|some\s+)?(?:futuristic|cyberpunk|realistic|cinematic|beautiful|3d|hd|8k|4k|fantasy|concept|digital|stylized)\b/i,
    
    // 5. Explicit AI keywords
    /\b(?:ai\s+image|ai\s+photo|ai\s+picture|ai\s+art|ai\s+artwork|ai\s+illustration|ai\s+generation)\b/i,
    /\b(?:generate|create|make|draw|render)\s+(?:an?\s+)?ai\b/i,
    
    // 6. Telugu / English mixed generation patterns
    /\b(?:generate|create|tayaru|chesi)\s*(?:chesi\s+ivu|chesi\s+ivvu|cheyyi|ivvu|ivvandi)\b/i,
    /\b(?:image|photo|picture|pic)\s+.*?(?:generate|create|cheyyi|chesi|tayaru|ivvu)/i,
    /\b(?:kalsi|kalisi)\s+.*?(?:image|photo|picture)\s*(?:generate|create|cheyyi|chesi|ivvu)/i,
    /\b(?:image\s+generate\s+cheyyi|image\s+generate\s+chesi\s+ivu|photo\s+create\s+cheyyi|create\s+chesi\s+ivu|generate\s+chesi\s+ivu|nuvu\s+generate\s+chesi\s+ivu|nuvve\s+generate\s+cheyyi)\b/i,
    /\b(?:image\s+tayaru\s+cheyyi|photo\s+tayaru\s+cheyyi)\b/i,

    // 7. Compact and space-free generation keywords
    /(?:generatechesi|createchesi|generatecheyyi|createcheyyi|imagegenerate|photocreate|generateimage|createimage)/i
  ];

  return explicitAIPatterns.some(pat => pat.test(lower) || pat.test(compact));
}

const KNOWN_ENTITIES_LIST = [
  'allu arjun', 'virat kohli', 'ms dhoni', 'rohit sharma', 'pawan kalyan',
  'mahesh babu', 'ram charan', 'jr ntr', 'ntr', 'prabhas', 'shahrukh khan',
  'salman khan', 'lord krishna', 'krishna', 'lord rama', 'lord shiva',
  'iron man', 'batman', 'superman', 'spiderman'
];

/**
 * Returns true if the query is a follow-up generation request building on previous context.
 */
function isFollowUpGenerationRequest(text, conversationContext) {
  if (!text || text.trim().length < 2) return false;
  const lower = text.trim().toLowerCase();

  const followUpPatterns = [
    /^(?:nuvu|nuvve)\s+(?:generate|create)\s*(?:chesi\s+ivu|chesi\s+ivvu|cheyyi|ivvu)?$/i,
    /\b(?:inkoka|inko|another|different|malli|one\s+more)\s+(?:style\s+loo|style\s+lo|style|variation|type)?\s*(?:generate|create|cheyyi|chesi\s+ivu|make)?\b/i,
    /^(?:generate\s+in\s+another\s+style|make\s+another\s+one|create\s+another\s+one|generate\s+another\s+one|try\s+another\s+style)$/i,
    /^(?:generate\s+cheyyi|create\s+cheyyi|generate\s+chesi\s+ivu)$/i,
  ];

  const matchesPattern = followUpPatterns.some(pat => pat.test(lower));
  if (!matchesPattern) return false;

  if (conversationContext && conversationContext.messages && conversationContext.messages.length > 0) {
    return true;
  }
  return matchesPattern;
}

/**
 * Returns true if multiple entities/persons are combined in a composition generation request.
 */
function isMultiEntityGenerationRequest(text) {
  if (!text || text.trim().length < 5) return false;
  const lower = text.trim().toLowerCase();
  const compact = lower.replace(/[^a-z0-9]/g, '');

  const knownAliases = [
    ['allu arjun', 'alluarjun'],
    ['virat kohli', 'viratkohli', 'kohli'],
    ['ms dhoni', 'msdhoni', 'dhoni'],
    ['rohit sharma', 'rohitsharma'],
    ['pawan kalyan', 'pawankalyan'],
    ['mahesh babu', 'maheshbabu'],
    ['ram charan', 'ramcharan'],
    ['jr ntr', 'jrntr', 'junior ntr', 'ntr'],
    ['prabhas'],
    ['shah rukh khan', 'shahrukh khan', 'shahrukhkhan', 'srk'],
    ['salman khan', 'salmankhan'],
    ['lord krishna', 'krishna'],
    ['lord rama', 'rama'],
    ['lord shiva', 'shiva']
  ];

  let matchedEntities = 0;
  for (const group of knownAliases) {
    if (group.some(alias => lower.includes(alias) || compact.includes(alias.replace(/\s+/g, '')))) {
      matchedEntities++;
    }
  }

  if (matchedEntities >= 2) {
    const hasComposition = /\b(?:kalsi|kalisi|together|with|and|combined|photo|image|picture|pakkana)\b/i.test(lower) ||
      /(?:kalsi|kalisi|together|with|and|pakkana)/i.test(compact);
    const hasAction = /\b(?:generate|create|make|draw|render|chesi|cheyyi|ivvu|ivvandi|tayaru)\b/i.test(lower) ||
      /(?:generate|create|chesi|cheyyi|ivvu)/i.test(compact);
    if (hasComposition || hasAction) return true;
  }
  return false;
}


/**
 * Returns true if user asks for a structured list with photos/images.
 */
function isListWithImagesRequest(text) {
  if (!text || text.trim().length < 5) return false;
  const lower = text.trim().toLowerCase();

  const listPatterns = [
    /\b(?:top\s+\d+|\d+\s+top|list\s+of|\d+\s+best|best\s+\d+)\s+.*(?:names?\s+and\s+(?:photos?|images?|pictures?)|with\s+(?:photos?|images?|pictures?)|photos?\s+and\s+names?|images?\s+and\s+names?)/i,
    /\b(?:top\s+\d+|\d+\s+top|list\s+of|\d+\s+best)\s+.*(?:celebrities|cricketers|actors|actresses|places|waterfalls|monuments|cities|destinations|leaders|movies)\s+.*(?:photos?|images?|pictures?)/i,
    /\b(?:names?\s+and\s+(?:photos?|images?|pictures?)|photos?\s+and\s+names?)\b/i,
    /\b(?:top\s+\d+|\d+\s+top)\s+.*(?:photos?\s+naku\s+ivu|images?\s+naku\s+ivu|photos?\s+chupinchu|images?\s+chupinchu)/i,
  ];

  return listPatterns.some(pat => pat.test(lower));
}

/**
 * Returns true if the user is requesting REAL web images/photos/pictures or visual search.
 */
function isRealImageSearchRequest(text) {
  if (!text || text.trim().length < 3) return false;
  const raw = text.trim();
  const lower = raw.toLowerCase();

  // CRITICAL GUARD: Never treat generation requests as real web image search
  const isGenerationCommand = /\b(?:generate|create|draw|render|make|paint|design|tayaru|illustrate)\b/i;
  if (isGenerationCommand.test(lower)) return false;

  // Guardrail: Explanations / informational questions
  const explainStarters = /^(?:what\s+is|what\s+are|explain|how\s+is|how\s+do|how\s+does|how\s+are|why\s+is|why\s+do|why\s+does|tell\s+me\s+about|describe\s+how|describe\s+why|define|summarize|compare|write)\b/i;
  if (explainStarters.test(lower)) return false;

  if (raw.endsWith('?')) {
    const hasExplicitImageWord = /\b(?:photos?|images?|pictures?|pics?|wallpapers?)\b/i.test(lower);
    if (!hasExplicitImageWord) return false;
  }

  const conversational = /^(?:hi|hello|hey|good\s+morning|good\s+evening|good\s+night|thanks|thank\s+you|ok|okay|bye)\b/i;
  if (conversational.test(lower)) return false;

  const imageSearchPatterns = [
    /\b(?:photos?|images?|pictures?|pictuers?|pichers?|imags?|pick?|fhotos?|picters?|wallpapers?)\b/i,
    /^(?:show\s+me|find|search|display|look\s+up|give\s+me)\s+(?:photos?|images?|pictures?|pictuers?|pichers?|pics?|wallpapers?)\b/i,
    /\b(?:image|photo|picture|pictuer|pic|photos|images|pictures|pictuers|pics)\s+(?:ivu|ivvandi|chupinchu|chupinchandi|kavali|kavale|chudali|ivvu)\b/i,
    /\b(?:hero|actor|actress|heroine)\s+.*?\b(?:photos?|images?|pictures?|pics?|wallpapers?|ivu|chupinchu)\b/i,
    /\b(?:real\s+photos?|real\s+images?|real\s+pictures?)\b/i,
    /\b(?:waterfalls?|falls|mountains?|hills?|beaches?|rivers?|forests?|sunset|sunrise|nature|landscapes?|flowers?|animals?|birds?|temples?|monuments?|forts?)\s+(?:in|at|near|with|and|of)\s+[\w\s]+/i,
    /\b(?:athirappilly|athirapally|jog\s+falls|dudhsagar|niagara)\s+(?:falls|waterfalls?)/i,
    /^(?:waterfalls?|mountains?|hills?|beaches?|nature|forests?|taj\s+mahal|eiffel\s+tower|charminar|athirappilly|athirapally)\b/i,
  ];

  return imageSearchPatterns.some(pat => pat.test(lower));
}

/**
 * Returns true if the user is asking to generate a document (PDF, DOCX, TXT, MD, Resume, Roadmap, etc.).
 */
function isDocumentGenerationRequest(text) {
  if (!text || text.trim().length < 3) return false;
  const lower = text.trim().toLowerCase();
  
  // Guard: If it's purely an image generation request without document format mentions, skip document gen
  const hasExplicitDocFormat = /\b(?:pdf|docx|word\s+document|txt|markdown|md|document|resume|cv|roadmap|cheatsheet)\b/i.test(lower);
  if (!hasExplicitDocFormat && /\b(?:generate|create|draw|make|render)\s+.*?\b(?:image|photo|picture|pic|artwork|painting|wallpaper)s?\b/i.test(lower)) {
    return false;
  }

  const docPatterns = [
    // 1. Explicit format mentions
    /\b(?:pdf|docx|word\s+document|txt|markdown|md)\b/i,
    // 2. Document creation actions
    /\b(?:create|generate|make|build|export|write|download|cheyyi|chesi|ivvu|ivvandi)\s+(?:a\s+|an\s+|my\s+)?(?:resume|cv|roadmap|report|notes|cover\s+letter|study\s+plan|documentation|readme|document|cheatsheet|guide)\b/i,
    // 3. Document types with creation
    /\b(?:resume|cv|roadmap|report|notes|cover\s+letter|study\s+plan|documentation|readme|cheatsheet|guide)\s+(?:create|generate|make|build|export|download|cheyyi|chesi|ivvu|ivvandi)\b/i,
    // 4. Specific roadmaps / notes
    /\b(?:python\s+roadmap|learning\s+roadmap|machine\s+learning\s+notes|ml\s+notes|cloud\s+computing\s+notes|python\s+notes|flask\s+notes|react\s+notes)\b/i
  ];

  return docPatterns.some(pat => pat.test(lower));
}

/**
 * Returns true if the user is asking for real-time live data (Weather, News, Sports, Finance, Current Events).
 */
function isLiveInformationRequest(text) {
  if (!text || text.trim().length < 3) return false;
  const lower = text.trim().toLowerCase();

  // Guard: Do not intercept explicit doc or image generation
  if (isDocumentGenerationRequest(text) || isExplicitAIImageRequest(text) || isRealImageSearchRequest(text)) {
    return false;
  }

  const livePatterns = [
    // Weather queries (e.g. "Weather in Bangalore today", "Bangalore weather", "What's the weather in Hyderabad?", "Weather in Chennai tomorrow")
    /\b(?:weather|temperature|forecast|rainfall|climate|rain)\b/i,
    // News queries (e.g. "Latest technology news today", "AI news today", "Latest tech news", "tech news today", "cricket news", "latest cricket news today")
    /\b(?:news|headlines?|breaking\s+news)\b/i,
    // Sports queries (e.g. "Current cricket score", "cricket score", "live ipl", "ipl score", "match score", "live score", "football score")
    /\b(?:cricket|ipl|score|match\s+result|scores?|football|fifa)\b/i,
    // Currency / Finance (e.g. "USD to INR today", "Dollar to rupee today", "100 USD in INR", "100 USD to INR")
    /\b(?:usd\s+to\s+inr|usd\s+in\s+inr|dollar\s+to\s+rupee|dollar\s+in\s+rupee|inr\s+to\s+usd|exchange\s+rate|bitcoin|btc|crypto|stock\s+price|gold\s+rate|gold\s+price)\b/i,
    /\b\d+\s*(?:usd|dollars?|\$)\s*(?:to|in|into)\s*(?:inr|rupees?)\b/i,
    // General live
    /\b(?:what\s+happened\s+today|latest\s+updates?\s+today)\b/i
  ];

  return livePatterns.some(pat => pat.test(lower));
}

/**
 * Master intent router adhering to priority order:
 * 1. DOCUMENT_GENERATION
 * 2. LIVE_INFORMATION
 * 3. AI_GENERATION (Explicit / Follow-up / Multi-entity)
 * 4. LIST_WITH_IMAGES
 * 5. REAL_IMAGE_SEARCH
 * 6. CHAT
 */
function determineIntent(text, conversationContext) {
  if (isDocumentGenerationRequest(text)) {
    return 'DOCUMENT_GENERATION';
  }
  if (isLiveInformationRequest(text)) {
    return 'LIVE_INFORMATION';
  }
  if (isExplicitAIImageRequest(text)) {
    return 'AI_GENERATION';
  }
  if (isFollowUpGenerationRequest(text, conversationContext)) {
    return 'AI_GENERATION';
  }
  if (isMultiEntityGenerationRequest(text)) {
    return 'AI_GENERATION';
  }
  if (isListWithImagesRequest(text)) {
    return 'LIST_WITH_IMAGES';
  }
  if (isRealImageSearchRequest(text)) {
    return 'REAL_IMAGE_SEARCH';
  }
  return 'CHAT';
}

/**
 * Extracts the subject from conversation history for follow-up requests like 'nuvu generate chesi ivu'
 */
function resolveFollowUpImagePrompt(query, conv) {
  if (!conv || !conv.messages || conv.messages.length === 0) return query;
  
  let lastSubject = '';
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    const msg = conv.messages[i];
    if (msg.type === 'image_generated') {
      lastSubject = msg.image_prompt || msg.content || '';
      break;
    } else if (msg.type === 'web_images' && msg.query) {
      lastSubject = msg.query;
      break;
    } else if (msg.role === 'user' && msg.content && msg.content !== query) {
      lastSubject = msg.content;
      break;
    }
  }

  if (!lastSubject) return query;

  lastSubject = lastSubject.replace(/^Image generated for:\s*"?|"?$/g, '').trim();

  const lower = query.toLowerCase();
  if (lower.includes('style') || lower.includes('variation') || lower.includes('different') || lower.includes('another')) {
    return `${lastSubject}, alternative artistic style variation`;
  }

  return lastSubject;
}


// ============================================================
// IMAGE GENERATION — Render generated image in chat
// ============================================================
/**
 * @param {string} originalPrompt   The user's original raw request
 * @param {string} imageDataUrl     base64 data URL OR direct https:// URL
 * @param {string} provider         Provider name e.g. "Pollinations AI"
 * @param {string} timestamp        ISO timestamp string
 * @param {string} [enhancedPrompt] The final prompt sent to the generator
 */
function appendGeneratedImageToDOM(originalPrompt, imageDataUrl, provider, timestamp, enhancedPrompt) {
  welcomeScreen.style.display = 'none';

  // ── Build timestamp string ────────────────────────────────────────────────
  const time    = timestamp ? new Date(timestamp) : new Date();
  const timeStr = String(time.getHours()).padStart(2, '0') + ':' +
                  String(time.getMinutes()).padStart(2, '0');

  // ── Show enhanced prompt line if it differs from original ─────────────────
  const showEnhanced = (
    enhancedPrompt &&
    enhancedPrompt.trim().toLowerCase() !== originalPrompt.trim().toLowerCase() &&
    enhancedPrompt.length > 10
  );

  // ── Outer message container ────────────────────────────────────────────────
  const msgDiv = document.createElement('div');
  msgDiv.className = 'message assistant-msg';

  const inner = document.createElement('div');
  inner.className = 'message-inner';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'N';

  const body = document.createElement('div');
  body.className = 'message-body';

  // Sender line
  const sender = document.createElement('div');
  sender.className = 'message-sender';
  sender.innerHTML = `NOVA <span class="message-time">${timeStr}</span>`;

  // Badge
  const badge = document.createElement('div');
  badge.className = 'generated-image-badge';
  badge.innerHTML =
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11">` +
    `<rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>` +
    `<circle cx="8.5" cy="8.5" r="1.5"/>` +
    `<polyline points="21 15 16 10 5 21"/>` +
    `</svg>` +
    ` AI Generated Image${provider ? ' &middot; ' + escapeHtml(provider) : ''}`;

  // Content wrapper
  const content = document.createElement('div');
  content.className = 'message-content generated-image-container';

  // Original request line
  const promptLine = document.createElement('p');
  promptLine.className = 'generated-image-prompt';
  promptLine.textContent = '\u2726 ' + originalPrompt;
  content.appendChild(promptLine);

  // Enhanced prompt line (optional)
  if (showEnhanced) {
    const enhLine = document.createElement('p');
    enhLine.className = 'generated-image-enhanced-prompt';
    enhLine.textContent = 'Prompt used: ' + enhancedPrompt;
    content.appendChild(enhLine);
  }

  // Image element
  const img = document.createElement('img');
  img.className = 'generated-image';
  img.src       = imageDataUrl;
  img.alt       = 'Generated: ' + originalPrompt;
  img.loading   = 'lazy';
  content.appendChild(img);

  // ── Action buttons ────────────────────────────────────────────────────────
  const actions = document.createElement('div');
  actions.className = 'generated-image-actions';

  // Regenerate button
  const regenBtn = document.createElement('button');
  regenBtn.className = 'msg-action-btn';
  regenBtn.title = 'Regenerate image';
  regenBtn.innerHTML =
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">` +
    `<path d="M1 4v6h6M23 20v-6h-6"/>` +
    `<path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/>` +
    `</svg><span>Regenerate</span>`;
  regenBtn.addEventListener('click', function() {
    sendImageGenerationRequest(originalPrompt);
  });

  // Download button — uses the same imageDataUrl as the img src
  const dlBtn = document.createElement('a');
  dlBtn.className = 'msg-action-btn';
  dlBtn.href      = imageDataUrl;
  dlBtn.download  = 'nova-generated.jpg';
  dlBtn.innerHTML =
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">` +
    `<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>` +
    `<polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>` +
    `</svg><span>Download</span>`;

  // Open button — uses Blob URL to reliably open image in new tab
  const openBtn = document.createElement('button');
  openBtn.className = 'msg-action-btn';
  openBtn.title = 'Open in new tab';
  openBtn.innerHTML =
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">` +
    `<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>` +
    `<polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>` +
    `</svg><span>Open</span>`;

  // Capture imageDataUrl in closure so it can't change after the element is built
  const capturedSrc = imageDataUrl;

  openBtn.addEventListener('click', function() {
    if (capturedSrc.startsWith('data:')) {
      // Convert base64 data URL -> Blob -> object URL -> write full HTML page
      try {
        const [header, b64data] = capturedSrc.split(',');
        const mimeMatch = header.match(/data:([^;]+);/);
        const mime      = mimeMatch ? mimeMatch[1] : 'image/jpeg';
        const byteStr   = atob(b64data);
        const bytes     = new Uint8Array(byteStr.length);
        for (let i = 0; i < byteStr.length; i++) bytes[i] = byteStr.charCodeAt(i);
        const blob      = new Blob([bytes], { type: mime });
        const blobUrl   = URL.createObjectURL(blob);

        const newTab = window.open('', '_blank');
        if (!newTab) {
          alert('Pop-up blocked. Please allow pop-ups for this site to open images in a new tab.');
          URL.revokeObjectURL(blobUrl);
          return;
        }
        newTab.document.write(
          '<!DOCTYPE html><html><head><title>NOVA Generated Image</title>' +
          '<style>body{margin:0;background:#111;display:flex;justify-content:center;' +
          'align-items:center;min-height:100vh;}' +
          'img{max-width:100%;max-height:100vh;object-fit:contain;}</style></head>' +
          '<body><img src="' + blobUrl + '" alt="Generated Image"></body></html>'
        );
        newTab.document.close();
        // Revoke after a short delay to allow the new tab to load the blob
        setTimeout(function() { URL.revokeObjectURL(blobUrl); }, 30000);
      } catch (err) {
        console.error('[NOVA] Open image error:', err);
        // Last-resort fallback: open data URL directly
        window.open(capturedSrc, '_blank');
      }
    } else {
      // Direct https:// URL — open normally
      window.open(capturedSrc, '_blank', 'noopener,noreferrer');
    }
  });

  actions.appendChild(regenBtn);
  actions.appendChild(dlBtn);
  actions.appendChild(openBtn);
  content.appendChild(actions);

  // Assemble
  body.appendChild(sender);
  body.appendChild(badge);
  body.appendChild(content);
  inner.appendChild(avatar);
  inner.appendChild(body);
  msgDiv.appendChild(inner);

  messagesList.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}


// ============================================================
// IMAGE GENERATION — Response Normalizer
// ============================================================
/**
 * Normalizes an image generation API response from /api/generate_image or /api/chat.
 * @param {object} data
 * @param {string} originalPromptFallback
 * @returns {{ success: boolean, displaySrc?: string, provider?: string, originalPrompt?: string, enhancedPrompt?: string, imageUrl?: string|null, error?: string }}
 */
function parseImageResponse(data, originalPromptFallback) {
  if (!data || typeof data !== 'object') {
    return { success: false, error: 'Invalid response object received from server.' };
  }

  // Check for explicit error flags
  if (data.success === false || data.is_error === true) {
    const errorMsg = data.error || data.message || data.detail || data.response || 'Image generation failed. Please try again.';
    return { success: false, error: errorMsg };
  }

  const mime = data.mime || 'image/jpeg';
  let displaySrc = null;
  let imageUrl = null;

  // Candidates ordered by priority: direct image, image_url, url, image_b64, image_data, b64_json
  const candidates = [
    data.image,
    data.image_url,
    data.url,
    data.image_b64,
    data.image_data,
    data.b64_json,
    data.imageUrl,
    data.image_link
  ];

  for (const val of candidates) {
    if (val && typeof val === 'string') {
      const trimmed = val.trim();
      if (!trimmed) continue;

      if (trimmed.startsWith('data:image/')) {
        displaySrc = trimmed;
        break;
      } else if (trimmed.startsWith('http://') || trimmed.startsWith('https://') || trimmed.startsWith('blob:')) {
        displaySrc = trimmed;
        imageUrl = trimmed;
        break;
      } else if (trimmed.length > 20 && !trimmed.includes(' ') && !trimmed.includes('\n')) {
        displaySrc = `data:${mime};base64,${trimmed}`;
        break;
      }
    }
  }

  // If candidate was base64 and image_url is also provided, preserve it
  if (!imageUrl && (data.image_url || data.url)) {
    const u = (data.image_url || data.url || '').trim();
    if (u.startsWith('http://') || u.startsWith('https://')) {
      imageUrl = u;
    }
  }

  if (displaySrc) {
    const originalPrompt = data.original_prompt || originalPromptFallback || 'Generated Image';
    const enhancedPrompt = data.prompt || data.image_prompt || originalPrompt;
    const provider       = data.provider || 'Image Generation';
    return {
      success: true,
      displaySrc: displaySrc,
      provider: provider,
      originalPrompt: originalPrompt,
      enhancedPrompt: enhancedPrompt,
      imageUrl: imageUrl
    };
  }

  const errorMsg = data.error || data.message || data.detail || 'Image generation service did not return image data.';
  return { success: false, error: errorMsg };
}


// ============================================================
// IMAGE GENERATION — API call and full flow
// ============================================================
async function sendImageGenerationRequest(prompt, originalDisplayQuery) {
  const displayUserText = originalDisplayQuery || prompt;
  // Get or create conversation
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  // Auto-title the conversation
  if (conv.messages.length === 0) {
    conv.title = generateTitle(displayUserText);
    chatTitleEl.textContent = conv.title;
  }

  // Add user message to DOM and storage
  const userMessage = {
    role: 'user',
    content: displayUserText,
    timestamp: new Date().toISOString(),
  };
  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  appendMessageToDOM('user', displayUserText, userMessage.timestamp);

  // Clear input
  userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  // Show loading state
  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch(`${API_URL}/api/generate_image`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt }),
    });

    const contentType = (res.headers.get('content-type') || '').toLowerCase();
    const httpStatus = res.status;

    console.log('[NOVA Debug] HTTP Status:', httpStatus);
    console.log('[NOVA Debug] Response Content-Type:', contentType);

    // ── 1. Raw Binary Image Bytes (image/png, image/jpeg, image/webp, image/*)
    if (contentType.startsWith('image/')) {
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      removeTypingIndicator(typingId);

      console.log('[NOVA Debug] Parsed Response Keys:', ['raw_image_blob']);
      console.log('[NOVA Debug] Image Source Type: Blob URL');

      const ts = new Date().toISOString();
      const assistantMessage = {
        role: 'assistant',
        type: 'image_generated',
        content: `Image generated for: "${prompt}"`,
        image_url: blobUrl,
        image_prompt: prompt,
        provider: 'Image Service',
        timestamp: ts,
        is_error: false,
      };
      conv.messages.push(assistantMessage);
      conv.updatedAt = ts;
      storage.saveConversation(conv);
      renderChatLists(searchInput.value);

      appendGeneratedImageToDOM(prompt, blobUrl, 'Image Service', ts, prompt);
      setAppState('READY');
      return;
    }

    // ── 2. JSON or text payload
    let rawText = '';
    let data = null;
    try {
      rawText = await res.text();
      data = JSON.parse(rawText);
    } catch (parseErr) {
      console.error('[NOVA Debug] Non-JSON response received:', {
        httpStatus,
        contentType,
        rawPreview: rawText ? rawText.substring(0, 300) : '<empty>'
      });
      removeTypingIndicator(typingId);
      appendMessageToDOM('assistant',
        `NOVA could not parse the image generation response (HTTP ${httpStatus}). Please try again.`,
        new Date().toISOString());
      setAppState('ERROR');
      setTimeout(() => setAppState('READY'), 3000);
      return;
    }

    removeTypingIndicator(typingId);

    console.log('[NOVA Debug] Parsed Response Keys:', Object.keys(data || {}));

    const parsed = parseImageResponse(data, prompt);

    if (parsed.success && parsed.displaySrc) {
      console.log('[NOVA Debug] Image Source Type:',
        parsed.displaySrc.startsWith('data:') ? 'Base64 Data URL' :
        (parsed.displaySrc.startsWith('blob:') ? 'Blob URL' : 'Direct URL')
      );

      const ts = new Date().toISOString();

      // Store only metadata in history — NOT the base64 blob
      const assistantMessage = {
        role: 'assistant',
        type: 'image_generated',
        content: `Image generated for: "${parsed.originalPrompt}"`,
        image_url:    parsed.imageUrl || null,
        image_prompt: parsed.enhancedPrompt,
        provider:     parsed.provider,
        timestamp:    ts,
        is_error:     false,
      };
      conv.messages.push(assistantMessage);
      conv.updatedAt = ts;
      storage.saveConversation(conv);
      renderChatLists(searchInput.value);

      appendGeneratedImageToDOM(parsed.originalPrompt, parsed.displaySrc, parsed.provider, ts, parsed.enhancedPrompt);
      setAppState('READY');

    } else {
      console.error('[NOVA Debug] Image generation response was unsuccessful or missing image data:', {
        httpStatus,
        contentType,
        data
      });
      const errorMsg = parsed.error ||
        'Image generation failed. Please try again or rephrase your prompt.';
      appendMessageToDOM('assistant', errorMsg, new Date().toISOString());
      setAppState('READY');
    }

  } catch (err) {
    console.error('[NOVA Debug] Image generation network error:', err);
    removeTypingIndicator(typingId);
    const errMsg = navigator.onLine
      ? 'Could not reach the image generation service. Please try again.'
      : 'You appear to be offline.';
    appendMessageToDOM('assistant', errMsg, new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}


// ============================================================
// WEB IMAGES — Render search gallery in chat
// ============================================================
/**
 * @param {string} query
 * @param {Array<{title: string, thumbnail: string, image_url: string, source_url: string, source_name: string}>} images
 * @param {string} provider
 * @param {string} timestamp
 */
function appendWebImagesToDOM(query, images, provider, timestamp) {
  welcomeScreen.style.display = 'none';

  const time = timestamp ? new Date(timestamp) : new Date();
  const timeStr = `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`;

  const msgDiv = document.createElement('div');
  msgDiv.className = 'message assistant-msg web-images-msg';

  let cardsHtml = '';
  if (images && images.length > 0) {
    cardsHtml = images.map(img => {
      const displayImg = img.thumbnail || img.image_url;
      const sourceName = img.provider || img.source_name || 'Web';
      return `
      <div class="web-image-card">
        <div class="web-image-thumb-wrap">
          <a href="${escapeHtml(img.source_url)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(img.title)}">
            <img class="web-image-thumb" src="${escapeHtml(displayImg)}" alt="${escapeHtml(img.title)}" loading="lazy" onerror="this.parentElement.parentElement.parentElement.style.display='none'"/>
          </a>
        </div>
        <div class="web-image-info">
          <div class="web-image-caption" title="${escapeHtml(img.title)}">${escapeHtml(img.title)}</div>
          <div class="web-image-footer">
            <span class="web-image-source" title="Source: ${escapeHtml(sourceName)}">Source: ${escapeHtml(sourceName)}</span>
            <a class="web-image-view-btn" href="${escapeHtml(img.source_url)}" target="_blank" rel="noopener noreferrer" title="Open source page">
              Open ↗
            </a>
          </div>
        </div>
      </div>
    `;
    }).join('');
  } else {
    cardsHtml = `<div class="web-images-empty" style="color:var(--text-secondary);font-size:0.85rem;">No real images found on the web for this query.</div>`;
  }

  msgDiv.innerHTML = `
    <div class="message-inner">
      <div class="message-avatar">N</div>
      <div class="message-body">
        <div class="message-sender">NOVA <span class="message-time">${timeStr}</span></div>
        <div class="web-images-container">
          <div class="web-images-header">
            <div class="web-images-badge">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13">
                <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
              </svg>
              <span>Real Images · Web Search</span>
            </div>
            <div class="web-images-title">Results for: <strong>${escapeHtml(query)}</strong></div>
          </div>
          <div class="web-images-grid">
            ${cardsHtml}
          </div>
        </div>
      </div>
    </div>
  `;

  messagesList.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}


// ============================================================
// WEB IMAGE SEARCH — API Call and Full Flow
// ============================================================
async function sendWebImageSearchRequest(query) {
  // Get or create conversation
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  // Auto-title the conversation
  if (conv.messages.length === 0) {
    conv.title = generateTitle(query);
    chatTitleEl.textContent = conv.title;
  }

  // Add user message to DOM and storage
  const userMessage = {
    role: 'user',
    content: query,
    timestamp: new Date().toISOString(),
  };
  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  appendMessageToDOM('user', query, userMessage.timestamp);

  // Clear input
  userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  // Show loading state
  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch(`${API_URL}/api/search_images`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });

    let data;
    try {
      data = await res.json();
    } catch (parseErr) {
      removeTypingIndicator(typingId);
      appendMessageToDOM('assistant',
        'Could not fetch web images. Please try again.',
        new Date().toISOString());
      setAppState('ERROR');
      setTimeout(() => setAppState('READY'), 3000);
      return;
    }

    removeTypingIndicator(typingId);

    if (data.success && data.images && data.images.length > 0) {
      const ts = new Date().toISOString();

      const assistantMessage = {
        role: 'assistant',
        type: 'web_images',
        query: query,
        content: `Web image results for: "${query}"`,
        images: data.images,
        provider: data.provider || 'Web Search',
        timestamp: ts,
        is_error: false,
      };
      conv.messages.push(assistantMessage);
      conv.updatedAt = ts;
      storage.saveConversation(conv);
      renderChatLists(searchInput.value);

      appendWebImagesToDOM(query, data.images, data.provider, ts);
      setAppState('READY');

    } else {
      const errorMsg = data.error || `No web images found for "${query}". Please try different keywords.`;
      appendMessageToDOM('assistant', errorMsg, new Date().toISOString());
      setAppState('READY');
    }

  } catch (err) {
    console.error('[NOVA] Web image search error:', err);
    removeTypingIndicator(typingId);
    const errMsg = navigator.onLine
      ? 'Could not reach the image search service. Please try again.'
      : 'You appear to be offline.';
    appendMessageToDOM('assistant', errMsg, new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}


// ============================================================
// DOCUMENT GENERATION — DOM Render & Request Handler
// ============================================================
function appendDocumentCardToDOM(docData, originalPrompt, timestamp) {
  welcomeScreen.style.display = 'none';

  const time = timestamp ? new Date(timestamp) : new Date();
  const timeStr = `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`;
  const fmt = (docData.format || 'pdf').toLowerCase();
  const badgeClass = `badge-${fmt}`;

  const msgDiv = document.createElement('div');
  msgDiv.className = 'message assistant-msg';

  const inner = document.createElement('div');
  inner.className = 'message-inner';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'N';

  const body = document.createElement('div');
  body.className = 'message-body';

  const sender = document.createElement('div');
  sender.className = 'message-sender';
  sender.innerHTML = `NOVA <span class="message-time">${timeStr}</span>`;

  const badge = document.createElement('div');
  badge.className = 'generated-image-badge';
  badge.innerHTML = `📄 Document Generated &middot; ${fmt.toUpperCase()}`;

  const content = document.createElement('div');
  content.className = 'message-content document-card-wrap';

  const promptLine = document.createElement('p');
  promptLine.className = 'generated-image-prompt';
  promptLine.textContent = '\u2726 ' + (originalPrompt || docData.title);
  content.appendChild(promptLine);

  // File Card
  const fileCard = document.createElement('div');
  fileCard.className = 'document-file-card';

  const left = document.createElement('div');
  left.className = 'document-file-left';

  const iconBadge = document.createElement('div');
  iconBadge.className = `document-icon-badge ${badgeClass}`;
  iconBadge.textContent = fmt.toUpperCase();

  const info = document.createElement('div');
  info.className = 'document-info';

  const title = document.createElement('div');
  title.className = 'document-title';
  title.textContent = docData.title || docData.filename || 'Generated Document';

  const meta = document.createElement('div');
  meta.className = 'document-meta-text';
  const sizeKb = Math.round((docData.file_size || 0) / 1024) || 1;
  meta.textContent = `${docData.filename || 'document.' + fmt} • ${sizeKb} KB • ${docData.sections_count || 3} sections`;

  info.appendChild(title);
  info.appendChild(meta);
  left.appendChild(iconBadge);
  left.appendChild(info);

  const actions = document.createElement('div');
  actions.className = 'document-actions';

  const fileDataUrl = `data:${docData.mime_type || 'application/octet-stream'};base64,${docData.base64_data}`;
  const fileName = docData.filename || `document.${fmt}`;

  const dlBtn = document.createElement('a');
  dlBtn.className = 'doc-download-btn';
  dlBtn.href = fileDataUrl;
  dlBtn.download = fileName;
  dlBtn.title = `Download ${fileName}`;
  dlBtn.innerHTML = `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" width="16" height="16">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
      <polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>
    </svg>
    <span>Download ${fmt.toUpperCase()}</span>
  `;

  actions.appendChild(dlBtn);

  // Add Open / View button for PDF and text formats
  if (fmt === 'pdf' || fmt === 'txt' || fmt === 'md') {
    const openBtn = document.createElement('button');
    openBtn.className = 'doc-open-btn';
    openBtn.title = `Open ${fileName} in new tab`;
    openBtn.innerHTML = `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
        <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
        <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
      </svg>
      <span>Open</span>
    `;
    openBtn.addEventListener('click', () => {
      try {
        const byteStr = atob(docData.base64_data);
        const bytes = new Uint8Array(byteStr.length);
        for (let i = 0; i < byteStr.length; i++) bytes[i] = byteStr.charCodeAt(i);
        const blob = new Blob([bytes], { type: docData.mime_type || 'application/pdf' });
        const blobUrl = URL.createObjectURL(blob);
        window.open(blobUrl, '_blank');
        setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
      } catch {
        window.open(fileDataUrl, '_blank');
      }
    });
    actions.appendChild(openBtn);
  }

  // Allow clicking iconBadge to trigger download
  iconBadge.title = `Click to download ${fileName}`;
  iconBadge.addEventListener('click', () => {
    dlBtn.click();
  });

  fileCard.appendChild(left);
  fileCard.appendChild(actions);
  content.appendChild(fileCard);

  // Optional summary note
  if (docData.summary) {
    const summaryP = document.createElement('p');
    summaryP.style.fontSize = '0.85rem';
    summaryP.style.color = 'var(--text-secondary)';
    summaryP.style.marginTop = '6px';
    summaryP.textContent = docData.summary;
    content.appendChild(summaryP);
  }

  body.appendChild(sender);
  body.appendChild(badge);
  body.appendChild(content);
  inner.appendChild(avatar);
  inner.appendChild(body);
  msgDiv.appendChild(inner);

  messagesList.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendDocumentGenerationRequest(prompt, originalText, imageB64 = null, imageMime = 'image/jpeg') {
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  if (conv.messages.length === 0) {
    conv.title = generateTitle(originalText || prompt);
    chatTitleEl.textContent = conv.title;
  }

  // If no explicit image passed, check if prompt references an existing image in chat
  if (!imageB64 && conv.messages && conv.messages.length > 0) {
    const lowerP = (prompt || '').toLowerCase();
    if (lowerP.includes('image') || lowerP.includes('photo') || lowerP.includes('picture') || lowerP.includes('convert') || lowerP.includes('idi') || lowerP.includes('ee')) {
      for (let i = conv.messages.length - 1; i >= 0; i--) {
        const m = conv.messages[i];
        if (m.image && m.image.startsWith('data:image')) {
          imageB64 = m.image.split(',')[1];
          imageMime = m.image.split(';')[0].replace('data:', '') || 'image/jpeg';
          break;
        } else if (m.image_b64) {
          imageB64 = m.image_b64;
          imageMime = m.mime || 'image/jpeg';
          break;
        }
      }
    }
  }

  const userMessage = {
    role: 'user',
    content: originalText || prompt,
    timestamp: new Date().toISOString(),
    image: imageB64 ? `data:${imageMime};base64,${imageB64}` : null
  };
  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  appendMessageToDOM('user', originalText || prompt, userMessage.timestamp, userMessage.image);

  userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  const detectedFmt = (prompt.toLowerCase().match(/\b(pdf|docx|word|txt|markdown|md)\b/) || ['pdf'])[0];
  console.log('[NOVA Document] Format detected:', detectedFmt);
  console.log('[NOVA Document] API called: /api/generate_document');

  try {
    const payload = { prompt: prompt };
    if (imageB64) {
      payload.image = imageB64;
      payload.image_mime = imageMime;
    }

    const res = await fetch(`${API_URL}/api/generate_document`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    console.log('[NOVA API] Status:', res.status);
    const data = await res.json();
    console.log('[NOVA API] Response:', data);

    removeTypingIndicator(typingId);

    if (data.success) {
      console.log('[NOVA Document] File received:', data.filename);
      console.log('[NOVA Document] Download ready:', data.file_size, 'bytes');

      const ts = data.timestamp || new Date().toISOString();
      const assistantMessage = {
        role: 'assistant',
        type: 'document_generated',
        content: `Generated document: ${data.filename}`,
        doc_data: data,
        timestamp: ts
      };
      conv.messages.push(assistantMessage);
      conv.updatedAt = ts;
      storage.saveConversation(conv);
      renderChatLists(searchInput.value);

      appendDocumentCardToDOM(data, originalText || prompt, ts);
      setAppState('READY');
    } else {
      throw new Error(data.error || 'Document generation failed');
    }
  } catch (err) {
    console.error('[NOVA Document] Error:', err);
    removeTypingIndicator(typingId);
    appendMessageToDOM('assistant', `⚠️ **Document Generation Error**: ${err.message || 'Could not compile document.'}`, new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}


// ============================================================
// LIVE INFORMATION — DOM Render & Request Handler
// ============================================================
function appendLiveInfoToDOM(liveData, originalQuery, timestamp) {
  welcomeScreen.style.display = 'none';

  const time = timestamp ? new Date(timestamp) : new Date();
  const timeStr = `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`;
  const category = (liveData.category || 'current_info').toLowerCase();

  const msgDiv = document.createElement('div');
  msgDiv.className = 'message assistant-msg';

  const inner = document.createElement('div');
  inner.className = 'message-inner';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = 'N';

  const body = document.createElement('div');
  body.className = 'message-body';

  const sender = document.createElement('div');
  sender.className = 'message-sender';
  sender.innerHTML = `NOVA <span class="message-time">${timeStr}</span>`;

  const badge = document.createElement('div');
  badge.className = 'generated-image-badge';
  badge.innerHTML = `⚡ Live Real-Time &middot; ${escapeHtml(liveData.source || 'Live Search')}`;

  const content = document.createElement('div');
  content.className = 'message-content live-info-container';

  const card = document.createElement('div');
  card.className = 'live-card';

  // Live card header
  const header = document.createElement('div');
  header.className = 'live-header';
  header.innerHTML = `
    <span class="live-pill pulse">${escapeHtml(category)}</span>
    <span class="live-source-meta">${escapeHtml(liveData.source || 'Live Index')} &bull; ${timeStr}</span>
  `;
  card.appendChild(header);

  if (category === 'weather' && liveData.temperature_c !== undefined) {
    // Weather Widget
    const weatherBody = document.createElement('div');
    weatherBody.innerHTML = `
      <div class="weather-hero">
        <div>
          <div class="weather-temp">${liveData.temperature_c}°C <span>/ ${liveData.temperature_f}°F</span></div>
          <div style="font-size:0.85rem;color:var(--text-muted);">${escapeHtml(liveData.location || 'Current Location')}</div>
        </div>
        <div class="weather-condition">${liveData.condition || 'Clear'}</div>
      </div>
      <div class="weather-details-grid">
        <div class="weather-metric-item"><span class="weather-metric-label">Wind</span><span class="weather-metric-val">${liveData.wind_kmh || 0} km/h</span></div>
        <div class="weather-metric-item"><span class="weather-metric-label">Humidity</span><span class="weather-metric-val">${liveData.humidity_pct || 50}%</span></div>
        <div class="weather-metric-item"><span class="weather-metric-label">Status</span><span class="weather-metric-val" style="color:var(--accent-green);">Live 🟢</span></div>
      </div>
    `;
    card.appendChild(weatherBody);
  } else if ((category === 'news' || category === 'sports') && liveData.articles && liveData.articles.length > 0) {
    // News / Sports Articles Feed
    const newsList = document.createElement('div');
    newsList.className = 'news-articles-list';
    liveData.articles.slice(0, 4).forEach(art => {
      const artEl = document.createElement('a');
      artEl.className = 'news-article-item';
      artEl.href = art.url || '#';
      artEl.target = '_blank';
      artEl.rel = 'noopener noreferrer';
      artEl.innerHTML = `
        <div class="news-article-title">${escapeHtml(art.title)}</div>
        <div class="news-article-snippet">${escapeHtml(art.snippet || art.title)}</div>
      `;
      newsList.appendChild(artEl);
    });
    card.appendChild(newsList);
  } else if (category === 'finance' && liveData.rate) {
    // Finance Rate & Currency Conversion
    const finBody = document.createElement('div');
    const amount = Number(liveData.amount || 1);
    const converted = Number(liveData.converted_value || liveData.rate);
    const rate = Number(liveData.rate);

    if (amount > 1) {
      finBody.innerHTML = `
        <div style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">${escapeHtml(liveData.symbol || 'USD/INR')} Conversion</div>
        <div class="finance-highlight">${amount} USD = ₹${converted.toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2})} INR</div>
        <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">Current Live Exchange Rate: 1 USD = ₹${rate.toFixed(2)} INR</div>
      `;
    } else {
      finBody.innerHTML = `
        <div style="font-size:0.85rem;color:var(--text-secondary);font-weight:600;">${escapeHtml(liveData.symbol || 'USD/INR')} Exchange Rate</div>
        <div class="finance-highlight">1 USD = ₹${rate.toFixed(2)} INR</div>
        <div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px;">Live foreign currency conversion rate.</div>
      `;
    }
    card.appendChild(finBody);
  } else {
    // General / Sports / Other live summary
    const generalBody = document.createElement('div');
    generalBody.innerHTML = renderMarkdown(liveData.summary || 'Live information retrieved.');
    card.appendChild(generalBody);
  }

  content.appendChild(card);
  body.appendChild(sender);
  body.appendChild(badge);
  body.appendChild(content);
  inner.appendChild(avatar);
  inner.appendChild(body);
  msgDiv.appendChild(inner);

  messagesList.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendLiveInfoRequest(query) {
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  if (conv.messages.length === 0) {
    conv.title = generateTitle(query);
    chatTitleEl.textContent = conv.title;
  }

  const userMessage = {
    role: 'user',
    content: query,
    timestamp: new Date().toISOString()
  };
  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  appendMessageToDOM('user', query, userMessage.timestamp);

  userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  console.log('[NOVA Live] API called: /api/live_info');

  try {
    const res = await fetch(`${API_URL}/api/live_info`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query })
    });

    console.log('[NOVA API] Status:', res.status);
    const data = await res.json();
    console.log('[NOVA API] Response:', data);

    removeTypingIndicator(typingId);

    if (data.success) {
      console.log('[NOVA Live] Type detected:', data.category);
      console.log('[NOVA Live] Data received:', data);

      const ts = data.timestamp || new Date().toISOString();
      const assistantMessage = {
        role: 'assistant',
        type: 'live_info',
        content: data.summary || 'Live information retrieved.',
        live_data: data,
        timestamp: ts
      };
      conv.messages.push(assistantMessage);
      conv.updatedAt = ts;
      storage.saveConversation(conv);
      renderChatLists(searchInput.value);

      appendLiveInfoToDOM(data, query, ts);
      setAppState('READY');
    } else {
      throw new Error(data.error || 'Live info fetch failed');
    }
  } catch (err) {
    console.error('[NOVA Live] Error:', err);
    removeTypingIndicator(typingId);
    appendMessageToDOM('assistant', `⚠️ **Live Information Service Error**: ${err.message || 'Could not retrieve live information at this moment.'}`, new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}


// ============================================================
// LIST WITH IMAGES — Structured List + Real Entity Image Fetch
// ============================================================
async function sendListWithImagesRequest(query) {
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  if (conv.messages.length === 0) {
    conv.title = generateTitle(query);
    chatTitleEl.textContent = conv.title;
  }

  const userMessage = {
    role: 'user',
    content: query,
    timestamp: new Date().toISOString(),
  };
  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);
  appendMessageToDOM('user', query, userMessage.timestamp);

  userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: query,
        history: conv.messages.slice(-8, -1).map(m => ({ role: m.role, content: m.content || '' })),
        language: languageSelect.value,
        search_mode: 'auto',
      }),
    });

    const data = await res.json();
    removeTypingIndicator(typingId);

    const chatResponseText = data.response || data.error || '';
    const ts = new Date().toISOString();

    // Extract entities from list items (e.g. 1. Virat Kohli, 2. MS Dhoni)
    const lines = chatResponseText.split('\n');
    const entityNames = [];
    for (const line of lines) {
      const match = line.match(/^(?:\d+[\.\)]|\*|\-)\s+\*{0,2}([\w\s\.\-]{3,40}?)\*{0,2}(?::|\s*[-–—]|\s*\(|$)/);
      if (match && match[1]) {
        const cleanName = match[1].replace(/[*_#]/g, '').trim();
        if (cleanName.length >= 3 && !['name', 'celebrity', 'cricketer', 'waterfall', 'top', 'rank'].includes(cleanName.toLowerCase())) {
          entityNames.push(cleanName);
        }
      }
      if (entityNames.length >= 6) break;
    }

    // Search real images for each individual entity
    const entityImages = [];
    if (entityNames.length > 0) {
      const searchPromises = entityNames.slice(0, 6).map(async (name) => {
        try {
          const imgRes = await fetch(`${API_URL}/api/search_images`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: name }),
          });
          const imgData = await imgRes.json();
          if (imgData.success && imgData.images && imgData.images.length > 0) {
            const first = imgData.images[0];
            return {
              title: name,
              thumbnail: first.thumbnail || first.image_url,
              image_url: first.image_url,
              source_url: first.source_url,
              provider: first.provider || 'Wikimedia Commons',
            };
          }
        } catch {
          return null;
        }
        return null;
      });

      const fetched = await Promise.all(searchPromises);
      for (const item of fetched) {
        if (item) entityImages.push(item);
      }
    }

    const assistantMessage = {
      role: 'assistant',
      content: chatResponseText,
      timestamp: ts,
      web_search_used: data.web_search_used || false,
      sources: data.sources || [],
      images: entityImages,
    };
    conv.messages.push(assistantMessage);
    conv.updatedAt = ts;
    storage.saveConversation(conv);
    renderChatLists(searchInput.value);

    // Render list response
    appendMessageToDOM('assistant', chatResponseText, ts, null, null, data.web_search_used, data.sources);

    // Render photo gallery for list entities
    if (entityImages.length > 0) {
      appendWebImagesToDOM(`Photos for: ${query}`, entityImages, 'Web Search', ts);
    }
    setAppState('READY');

  } catch (err) {
    console.error('[NOVA] List with images error:', err);
    removeTypingIndicator(typingId);
    appendMessageToDOM('assistant', 'Could not retrieve list and photos. Please try again.', new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}


// ============================================================
// MESSAGE RENDERING
// ============================================================
function appendMessageToDOM(role, content, timestamp, imageDataUrl, fileName, webSearchUsed = false, sources = [], webSearchFallback = false, visionSubintent = null) {
  // Hide welcome screen once messages appear
  welcomeScreen.style.display = 'none';

  const msgDiv = document.createElement('div');
  msgDiv.className = `message ${role === 'user' ? 'user-msg' : 'assistant-msg'}`;
  if (!webSearchUsed && !sources.length) msgDiv.style.animation = ''; // keep default animate

  const time = timestamp ? new Date(timestamp) : new Date();
  const timeStr = `${String(time.getHours()).padStart(2, '0')}:${String(time.getMinutes()).padStart(2, '0')}`;

  const avatarLabel = role === 'user' ? 'You' : 'N';
  const senderName = role === 'user' ? 'You' : 'NOVA';

  let contentHtml = '';
  
  // File badge
  if (fileName) {
    contentHtml += `<div class="message-file-badge">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
      </svg>
      <span>${escapeHtml(fileName)}</span>
    </div>`;
  }

  // Image preview
  if (imageDataUrl) {
    contentHtml += `<img class="message-image" src="${imageDataUrl}" alt="Uploaded image" loading="lazy">`;
  }

  // Vision subintent badge
  if (role === 'assistant' && visionSubintent) {
    let badgeText = 'Image Analysis';
    let badgeClass = 'vision-badge-qa';
    if (visionSubintent === 'ocr') {
      badgeText = '🔍 OCR Text Extracted';
      badgeClass = 'vision-badge-ocr';
    } else if (visionSubintent === 'error_analysis') {
      badgeText = '🛠️ Error Debugger & Fix';
      badgeClass = 'vision-badge-error';
    } else if (visionSubintent === 'ui_analysis') {
      badgeText = '🎨 UI / UX Design Audit';
      badgeClass = 'vision-badge-ui';
    } else if (visionSubintent === 'qa') {
      badgeText = '👁️ Vision Q&A';
      badgeClass = 'vision-badge-qa';
    }
    contentHtml += `<div class="vision-subintent-badge ${badgeClass}">${badgeText}</div>`;
  }

  // Message content (markdown for assistant, plain for user)
  // Web-search badge or Fallback badge goes above content for assistant messages
  if (role === 'assistant') {
    if (webSearchUsed) {
      contentHtml += `<div class="web-search-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
        Searched the web
      </div>`;
    } else if (webSearchFallback) {
      contentHtml += `<div class="web-search-fallback-badge">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        Live Web Search Unavailable (API Plan Quota) — Answered from Training Knowledge
      </div>`;
    }
  }
  if (content) {
    if (role === 'assistant') {
      contentHtml += `<div class="message-content">${renderMarkdown(content)}</div>`;
    } else {
      contentHtml += `<div class="message-content">${escapeHtml(content).replace(/\n/g, '<br>')}</div>`;
    }
  }

  // Message actions (only for assistant messages)
  let actionsHtml = '';
  if (role === 'assistant') {
    actionsHtml = `
      <div class="message-actions">
        <button class="msg-action-btn copy-msg-btn" title="Copy response">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
          </svg>
          <span>Copy</span>
        </button>
        <button class="msg-action-btn share-msg-btn" title="Share response">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
          </svg>
          <span>Share</span>
        </button>
        <button class="msg-action-btn regenerate-btn" title="Regenerate response">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14">
            <polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/>
          </svg>
          <span>Regenerate</span>
        </button>
      </div>
    `;
  }

  // Sources panel (below actions)
  let sourcesHtml = '';
  if (role === 'assistant' && sources && sources.length > 0) {
    const sourceItems = sources.map((s, i) => `
      <a class="source-link" href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">
        <span class="source-num">${i + 1}</span>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
        ${escapeHtml(s.title || s.url)}
      </a>`).join('');
    sourcesHtml = `
      <div class="sources-panel">
        <div class="sources-title">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="11" height="11"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          Sources
        </div>
        <div class="sources-list">${sourceItems}</div>
      </div>`;
  }

  msgDiv.innerHTML = `
    <div class="message-inner">
      <div class="message-avatar">${avatarLabel}</div>
      <div class="message-body">
        <div class="message-sender">${senderName} <span class="message-time">${timeStr}</span></div>
        ${contentHtml}
        ${actionsHtml}
        ${sourcesHtml}
      </div>
    </div>
  `;

  // Attach action handlers
  if (role === 'assistant') {
    const copyBtn = msgDiv.querySelector('.copy-msg-btn');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => {
        navigator.clipboard.writeText(content || '').then(() => {
          copyBtn.querySelector('span').textContent = 'Copied!';
          setTimeout(() => { copyBtn.querySelector('span').textContent = 'Copy'; }, 2000);
        }).catch(() => {
          // Fallback for older browsers
          const ta = document.createElement('textarea');
          ta.value = content || '';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          copyBtn.querySelector('span').textContent = 'Copied!';
          setTimeout(() => { copyBtn.querySelector('span').textContent = 'Copy'; }, 2000);
        });
      });
    }

    const shareBtn = msgDiv.querySelector('.share-msg-btn');
    if (shareBtn) {
      shareBtn.addEventListener('click', async () => {
        const shareText = content || '';
        if (navigator.share) {
          try {
            await navigator.share({
              title: 'Shared from NOVA AI',
              text: shareText,
            });
            shareBtn.querySelector('span').textContent = 'Shared!';
            setTimeout(() => { shareBtn.querySelector('span').textContent = 'Share'; }, 2000);
          } catch (err) {
            // User cancelled — no action needed
          }
        } else {
          // Clipboard fallback for unsupported browsers
          try {
            await navigator.clipboard.writeText(shareText);
          } catch {
            const ta = document.createElement('textarea');
            ta.value = shareText;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
          }
          showToast('Response copied. You can now share it.', 'info');
          shareBtn.querySelector('span').textContent = 'Copied!';
          setTimeout(() => { shareBtn.querySelector('span').textContent = 'Share'; }, 2500);
        }
      });
    }

    const regenBtn = msgDiv.querySelector('.regenerate-btn');
    if (regenBtn) {
      regenBtn.addEventListener('click', () => regenerateLastResponse());
    }
  }

  messagesList.appendChild(msgDiv);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

function appendTypingIndicator() {
  const id = 'typing-' + Date.now();
  const div = document.createElement('div');
  div.className = 'typing-indicator';
  div.id = id;
  div.innerHTML = `
    <div class="message-inner">
      <div class="message-avatar" style="background:var(--bg-tertiary);border:1px solid var(--border-accent);color:var(--accent-cyan);">N</div>
      <div class="message-body">
        <div class="message-sender">NOVA</div>
        <div class="typing-dots">
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
          <div class="typing-dot"></div>
        </div>
      </div>
    </div>
  `;
  messagesList.appendChild(div);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return id;
}

function removeTypingIndicator(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

// ============================================================
// SEND MESSAGE
// ============================================================
async function sendMessage(overrideText = null) {
  console.log("NOVA VERSION: AI-ROUTING-FIX-2026");
  if (appState === 'THINKING...') return;

  const query = overrideText || userInput.value.trim();
  const hasImage = fileUploadManager.pendingImage;
  const hasFile  = fileUploadManager.pendingFile;

  if (!query && !hasImage && !hasFile) return;

  // Check monetization limits
  if (!planManager.canSendMessage()) {
    showToast('Daily request limit reached. Upgrade to Premium for unlimited access.', 'error');
    return;
  }

  // ── Image to PDF conversion if image is attached and PDF requested ──
  if (hasImage && query && isDocumentGenerationRequest(query)) {
    console.log('[NOVA Route] Image to PDF requested: Calling /api/generate_document');
    const b64 = hasImage.base64;
    const mime = hasImage.mime;
    fileUploadManager.clear();
    await sendDocumentGenerationRequest(query, query, b64, mime);
    return;
  }

  // ── Intent Routing (Priority 1: Doc Gen -> Priority 2: Live Info -> Priority 3: AI Gen -> Priority 4: List -> Priority 5: Real Image -> Default: Chat) ──
  // Only fire for pure text messages (no file/image attachments).
  if (query && !hasImage && !hasFile) {
    const conv = getCurrentConversation();
    const intent = determineIntent(query, conv);

    console.log('[NOVA Intent] Query:', query);
    console.log('[NOVA Intent] Detected:', intent);

    if (intent === 'DOCUMENT_GENERATION') {
      console.log('[NOVA Route] Calling endpoint: /api/generate_document');
      await sendDocumentGenerationRequest(query, query);
      return;
    } else if (intent === 'LIVE_INFORMATION') {
      console.log('[NOVA Route] Calling endpoint: /api/live_info');
      await sendLiveInfoRequest(query);
      return;
    } else if (intent === 'AI_GENERATION') {
      console.log('[NOVA Route] Calling endpoint: /api/generate_image');
      let promptToSend = query;
      if (isFollowUpGenerationRequest(query, conv)) {
        promptToSend = resolveFollowUpImagePrompt(query, conv);
      }
      await sendImageGenerationRequest(promptToSend, query);
      return;
    } else if (intent === 'LIST_WITH_IMAGES') {
      console.log('[NOVA Route] Calling endpoint: /api/chat + /api/search_images (LIST_WITH_IMAGES)');
      await sendListWithImagesRequest(query);
      return;
    } else if (intent === 'REAL_IMAGE_SEARCH') {
      console.log('[NOVA Route] Calling endpoint: /api/search_images');
      await sendWebImageSearchRequest(query);
      return;
    } else {
      console.log('[NOVA Route] Calling endpoint: /api/chat');
    }
  }

  if (!overrideText) userInput.value = '';
  userInput.style.height = 'auto';
  updateSendButtonState();

  // Get or create conversation
  let conv = getCurrentConversation();
  if (!conv) {
    conv = createNewConversation();
    currentConversationId = conv.id;
  }

  // Auto-generate title from first user message
  if (conv.messages.length === 0 && query) {
    conv.title = generateTitle(query);
    chatTitleEl.textContent = conv.title;
  }

  // Build message record.
  // image DataURL is stored in `image` — base64 and MIME are derived from it
  // during regeneration, so we do NOT store image_base64 separately (avoids
  // writing up to 13 MB of duplicate base64 text into localStorage).
  // file_text and file_name are stored for file-based regeneration.
  const userMessage = {
    role: 'user',
    content: query,
    timestamp: new Date().toISOString(),
    image:     hasImage ? hasImage.dataUrl : null,  // DataURL — also used to derive base64 on regen
    fileName:  hasFile  ? hasFile.name     : null,  // display badge (backward-compat)
    file_name: hasFile  ? hasFile.name     : null,  // file name for regeneration
    file_text: hasFile  ? hasFile.text     : null   // extracted text for regeneration
  };

  conv.messages.push(userMessage);
  conv.updatedAt = new Date().toISOString();
  storage.saveConversation(conv);

  // Render user message
  appendMessageToDOM('user', query, userMessage.timestamp, userMessage.image, userMessage.fileName);

  // Prepare API payload
  const currentLang = languageSelect.value;
  
  // Build history from conversation (last 10 messages for context).
  // Strip image_base64 / image_mime — raw image data must never be sent
  // inside the conversation history array; it only belongs in the top-level
  // payload fields when the current message has an image attachment.
  const historyForAPI = conv.messages
    .filter(m => m.content) // Only include messages with text content
    .slice(-12, -1)          // Last 10 messages excluding the current one
    .map(m => ({ role: m.role, content: m.content })); // text only, no image data

  const payload = {
    message: query,
    history: historyForAPI,
    language: currentLang,
    search_mode: currentSearchMode      // 'auto' | 'web' | 'ai'
  };

  // Add image if present
  if (hasImage) {
    payload.image = hasImage.base64;
    payload.image_mime = hasImage.mime;
  }

  // Add file context if present
  if (hasFile) {
    payload.file_context = hasFile.text;
  }

  // Clear attachments
  fileUploadManager.clear();

  // Show typing indicator
  setAppState('THINKING...');
  const typingId = appendTypingIndicator();

  try {
    const res = await fetch(`${API_URL}/api/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });

    // Parse JSON — backend always returns JSON (even for errors)
    let data;
    try {
      data = await res.json();
    } catch (parseErr) {
      // Non-JSON response (e.g. Vercel 502 HTML page)
      removeTypingIndicator(typingId);
      const httpMsg = `NOVA backend returned an unexpected response (HTTP ${res.status}). The server may be restarting — please try again in a moment.`;
      appendMessageToDOM('assistant', httpMsg, new Date().toISOString());
      setAppState('ERROR');
      setTimeout(() => setAppState('READY'), 3000);
      return;
    }

    // If backend intercepted and returned a generated image
    if (data.type === 'image_generated' || data.image_b64 || data.image_data || (data.image_url && !hasImage && !hasFile)) {
      const parsed = parseImageResponse(data, query);
      if (parsed.success && parsed.displaySrc) {
        const ts = new Date().toISOString();
        const assistantMessage = {
          role: 'assistant',
          type: 'image_generated',
          content: `Image generated for: "${parsed.originalPrompt}"`,
          image_url: parsed.imageUrl || null,
          image_prompt: parsed.enhancedPrompt,
          provider: parsed.provider,
          timestamp: ts,
          is_error: false,
        };
        conv.messages.push(assistantMessage);
        conv.updatedAt = ts;
        storage.saveConversation(conv);
        renderChatLists(searchInput.value);
        appendGeneratedImageToDOM(parsed.originalPrompt, parsed.displaySrc, parsed.provider, ts, parsed.enhancedPrompt);
        setAppState('READY');
        return;
      }
    }

    // Backend returned a response field — display it regardless of is_error flag.
    // This covers: successful answers, rate-limit messages, quota errors, safety blocks, etc.
    if (data.response) {
      const assistantMessage = {
        role: 'assistant',
        content: data.response,
        timestamp: new Date().toISOString(),
        web_search_used: data.web_search_used || false,
        web_search_fallback: data.web_search_fallback || false,
        sources: data.sources || [],
        is_error: data.is_error || false,
        error_type: data.error_type || null
      };

      if (!data.is_error) {
        // Successful answer — save to conversation history
        conv.messages.push(assistantMessage);
        conv.updatedAt = new Date().toISOString();
        storage.saveConversation(conv);
        renderChatLists(searchInput.value);
        planManager.trackRequest();
        speakResponse(data.response, currentLang);
      }

      // Render the response (or error message from backend)
      appendMessageToDOM(
        'assistant',
        data.response,
        assistantMessage.timestamp,
        null, null,
        assistantMessage.web_search_used,
        assistantMessage.sources,
        assistantMessage.web_search_fallback,
        data.vision_subintent || null
      );
      setAppState('READY');

    } else if (data.error) {
      // Backend error without a 'response' field
      appendMessageToDOM('assistant', data.error, new Date().toISOString());
      setAppState('READY');
    } else {
      appendMessageToDOM('assistant', 'NOVA returned an empty response. Please try again.', new Date().toISOString());
      setAppState('READY');
    }

  } catch (err) {
    // fetch() itself threw — genuine network failure (server down, no internet, CORS, etc.)
    console.error('[NOVA] Network error:', err);
    removeTypingIndicator(typingId);

    let errorMsg;
    if (!navigator.onLine) {
      errorMsg = 'You appear to be offline. Please check your internet connection.';
    } else {
      errorMsg = 'Unable to connect to NOVA. The server may be starting up — please wait a moment and try again.';
    }

    appendMessageToDOM('assistant', errorMsg, new Date().toISOString());
    setAppState('ERROR');
    setTimeout(() => setAppState('READY'), 3000);
  }
}

function regenerateLastResponse() {
  const conv = getCurrentConversation();
  if (!conv || conv.messages.length < 2) return;

  // Find last user message
  let lastUserIdx = -1;
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].role === 'user') {
      lastUserIdx = i;
      break;
    }
  }

  if (lastUserIdx < 0) return;

  const lastUserMsg = conv.messages[lastUserIdx];

  // Remove last assistant message from conversation
  if (conv.messages[conv.messages.length - 1].role === 'assistant') {
    conv.messages.pop();
    storage.saveConversation(conv);
  }

  // Remove last assistant message from DOM
  const allMsgs = messagesList.querySelectorAll('.message.assistant-msg');
  if (allMsgs.length > 0) {
    allMsgs[allMsgs.length - 1].remove();
  }

  // Also remove the last user message from conversation so sendMessage can re-add it
  conv.messages.pop();
  storage.saveConversation(conv);
  const allUserMsgs = messagesList.querySelectorAll('.message.user-msg');
  if (allUserMsgs.length > 0) {
    allUserMsgs[allUserMsgs.length - 1].remove();
  }

  // If the original request had an image, restore it into the upload manager
  // so that sendMessage() can include it in the regenerated payload.
  // Derive base64 and MIME from the stored DataURL — no separate storage needed.
  // DataURL format: "data:<mime>;base64,<data>"
  if (lastUserMsg.image) {
    const dataUrl = lastUserMsg.image;
    const mimeMatch = dataUrl.match(/^data:([^;]+);base64,/);
    if (mimeMatch) {
      fileUploadManager.pendingImage = {
        dataUrl: dataUrl,                // DataURL for preview display
        base64:  dataUrl.split(',')[1],  // base64 portion for API payload
        mime:    mimeMatch[1],           // MIME type for API payload
        file:    null                    // File object not needed for regen
      };
      fileUploadManager.updatePreviewUI();
    }
  }

  // If the original request had a file, restore it into the upload manager
  // so that sendMessage() includes file_context in the regenerated payload.
  if (lastUserMsg.file_text && lastUserMsg.file_name) {
    fileUploadManager.pendingFile = {
      name: lastUserMsg.file_name,   // filename for display badge
      text: lastUserMsg.file_text,   // extracted text for API payload
      file: null                     // original File object not needed for regen
    };
    fileUploadManager.updatePreviewUI();
  }

  // Re-send with the original text (image/file now in fileUploadManager if applicable)
  sendMessage(lastUserMsg.content);
}

// ============================================================
// SPEECH SYNTHESIS (TTS) — Preserved from v1
// ============================================================
function speakResponse(text, langCode) {
  if (!isTTSEnabled || !('speechSynthesis' in window)) return;

  // Cancel any ongoing speech
  window.speechSynthesis.cancel();

  // Strip markdown for speech
  const plainText = text
    .replace(/```[\s\S]*?```/g, 'code block omitted')
    .replace(/`[^`]+`/g, '')
    .replace(/[#*_~\[\]]/g, '')
    .replace(/\n+/g, '. ')
    .substring(0, 500); // Limit speech length

  currentUtterance = new SpeechSynthesisUtterance(plainText);

  // Set voice language
  currentUtterance.lang = langCode || 'en-US';
  if (langCode === 'te') currentUtterance.lang = 'te-IN';
  else if (langCode === 'hi') currentUtterance.lang = 'hi-IN';
  else if (langCode === 'ta') currentUtterance.lang = 'ta-IN';
  else if (langCode === 'kn') currentUtterance.lang = 'kn-IN';

  // Select best voice
  const voices = window.speechSynthesis.getVoices();
  let matchedVoice = null;
  for (let v of voices) {
    if (v.lang.toLowerCase().includes(currentUtterance.lang.toLowerCase())) {
      matchedVoice = v;
      if (v.name.includes('Google') || v.name.includes('Natural')) break;
    }
  }
  if (matchedVoice) currentUtterance.voice = matchedVoice;

  currentUtterance.rate = 1.0;
  currentUtterance.volume = 1.0;

  currentUtterance.onstart = () => setAppState('SPEAKING...');
  currentUtterance.onend = () => setAppState('READY');
  currentUtterance.onerror = () => setAppState('READY');

  window.speechSynthesis.speak(currentUtterance);
}

// Ensure voices are loaded
if ('speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();
}

// ============================================================
// SPEECH RECOGNITION (STT) — Preserved from v1
// ============================================================
let recognition = null;
if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
  const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
  recognition = new SpeechRec();
  recognition.continuous = false;
  recognition.interimResults = false;

  recognition.onstart = () => {
    setAppState('LISTENING...');
    if (micBtn) micBtn.classList.add('listening');
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    if (userInput) {
      userInput.value = transcript;
      updateSendButtonState();
    }
    // Auto-send voice queries
    sendMessage();
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error:', event.error);
    setAppState('READY');
    if (micBtn) micBtn.classList.remove('listening');
    
    if (event.error === 'not-allowed') {
      showToast('Microphone access denied. Please allow microphone access in your browser settings.', 'error');
    } else if (event.error !== 'aborted') {
      showToast('Voice recognition failed. Please try again.', 'error');
    }
  };

  recognition.onend = () => {
    if (appState === 'LISTENING...') setAppState('READY');
    if (micBtn) micBtn.classList.remove('listening');
  };
}

function toggleVoiceRecognition() {
  if (!recognition) {
    showToast('Speech recognition is not supported in this browser. Please use Chrome, Safari, or Edge.', 'error');
    return;
  }

  if (appState === 'LISTENING...') {
    recognition.stop();
  } else {
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    
    const lang = languageSelect.value;
    if (lang === 'te') recognition.lang = 'te-IN';
    else if (lang === 'hi') recognition.lang = 'hi-IN';
    else if (lang === 'ta') recognition.lang = 'ta-IN';
    else if (lang === 'kn') recognition.lang = 'kn-IN';
    else recognition.lang = 'en-US';

    recognition.start();
  }
}

// ============================================================
// MINI HOLOGRAPHIC CANVAS (Welcome Screen)
// ============================================================
function drawMiniHolo() {
  const canvas = document.getElementById('mini-holo-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const H = canvas.height;
  
  ctx.clearRect(0, 0, W, H);
  
  const cx = W / 2;
  const cy = H / 2;
  const baseR = Math.min(W, H) * 0.35;
  const time = Date.now() * 0.001;

  // Determine color based on theme
  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const r = isDark ? 0 : 0;
  const g = isDark ? 229 : 151;
  const b = isDark ? 255 : 167;
  
  // Glow
  const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 1.5);
  glow.addColorStop(0, `rgba(${r},${g},${b},0.2)`);
  glow.addColorStop(0.5, `rgba(${r},${g},${b},0.05)`);
  glow.addColorStop(1, 'transparent');
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);

  // Rings
  const rings = [
    { r: 1.0, w: 2, a: 0.6, spd: 1.0, dash: null },
    { r: 0.85, w: 1.5, a: 0.4, spd: -1.5, dash: [8, 6] },
    { r: 0.7, w: 1, a: 0.3, spd: 2.0, dash: [4, 8] },
    { r: 0.55, w: 1.5, a: 0.35, spd: -1.0, dash: [12, 6] },
    { r: 0.4, w: 1, a: 0.25, spd: 2.5, dash: null }
  ];

  ctx.globalCompositeOperation = 'screen';
  rings.forEach(ring => {
    const radius = baseR * ring.r * (1 + 0.02 * Math.sin(time * 2));
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(time * ring.spd * 0.3);
    ctx.beginPath();
    ctx.arc(0, 0, radius, 0, Math.PI * 2);
    ctx.lineWidth = ring.w;
    ctx.strokeStyle = `rgba(${r},${g},${b},${ring.a})`;
    ctx.setLineDash(ring.dash || []);
    ctx.stroke();
    ctx.restore();
  });

  // Core dot
  ctx.globalCompositeOperation = 'source-over';
  const coreGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, baseR * 0.15);
  coreGlow.addColorStop(0, `rgba(${r},${g},${b},0.8)`);
  coreGlow.addColorStop(1, 'transparent');
  ctx.fillStyle = coreGlow;
  ctx.beginPath();
  ctx.arc(cx, cy, baseR * 0.15, 0, Math.PI * 2);
  ctx.fill();
  
  requestAnimationFrame(drawMiniHolo);
}

// ============================================================
// INPUT HANDLING
// ============================================================
function updateSendButtonState() {
  const hasText = userInput.value.trim().length > 0;
  const hasAttachment = fileUploadManager.hasPending();
  sendBtn.disabled = !(hasText || hasAttachment) || appState === 'THINKING...';
}

// Auto-grow textarea
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
  updateSendButtonState();
});

// Send on Enter (Shift+Enter for new line)
userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

sendBtn.addEventListener('click', () => sendMessage());
micBtn.addEventListener('click', toggleVoiceRecognition);

// TTS Toggle
ttsToggle.addEventListener('click', () => {
  isTTSEnabled = !isTTSEnabled;
  const onIcon = ttsToggle.querySelector('.tts-on-icon');
  const offIcon = ttsToggle.querySelector('.tts-off-icon');
  
  if (isTTSEnabled) {
    onIcon.style.display = 'block';
    offIcon.style.display = 'none';
  } else {
    onIcon.style.display = 'none';
    offIcon.style.display = 'block';
    if (window.speechSynthesis) window.speechSynthesis.cancel();
    if (appState === 'SPEAKING...') setAppState('READY');
  }
  
  const prefs = storage.getPreferences();
  prefs.ttsEnabled = isTTSEnabled;
  storage.savePreferences(prefs);
});

// ============================================================
// FIREBASE AUTHENTICATION CONTROLLER & STATE
// ============================================================
let currentUser = null;

// Auth DOM Elements
const authModalOverlay   = document.getElementById('auth-modal-overlay');
const authCloseBtn       = document.getElementById('auth-close-btn');
const tabLogin           = document.getElementById('tab-login');
const tabRegister        = document.getElementById('tab-register');
const googleSignInBtn    = document.getElementById('google-sign-in-btn');
const googleAuthContainer= document.getElementById('google-auth-container');
const loginForm          = document.getElementById('login-form');
const registerForm       = document.getElementById('register-form');
const verificationView   = document.getElementById('verification-view');
const forgotPwdForm      = document.getElementById('forgot-pwd-form');
const forgotPwdLink      = document.getElementById('forgot-pwd-link');
const backToLoginBtn     = document.getElementById('back-to-login-btn');
const authAlert          = document.getElementById('auth-alert');
const checkVerifiedBtn   = document.getElementById('check-verified-btn');
const resendEmailBtn     = document.getElementById('resend-email-btn');
const resendBtnText      = document.getElementById('resend-btn-text');
const verifyLogoutBtn    = document.getElementById('verify-logout-btn');
const verifyEmailDisplay = document.getElementById('verify-email-display');

// User Profile Top-Nav Elements
const userProfileWrapper = document.getElementById('user-profile-wrapper');
const userAvatarBtn      = document.getElementById('user-avatar-btn');
const userAvatarImg      = document.getElementById('user-avatar-img');
const userAvatarInitials = document.getElementById('user-avatar-initials');
const userProfileDropdown= document.getElementById('user-profile-dropdown');
const dropdownUserAvatar = document.getElementById('dropdown-user-avatar');
const dropdownUserName   = document.getElementById('dropdown-user-name');
const dropdownUserEmail  = document.getElementById('dropdown-user-email');
const dropdownUserBadge  = document.getElementById('dropdown-user-badge');
const dropdownBadgeText  = document.getElementById('dropdown-badge-text');
const dropdownAuthBtn    = document.getElementById('dropdown-auth-btn');
const dropdownAuthBtnText= document.getElementById('dropdown-auth-btn-text');
const dropdownLogoutBtn  = document.getElementById('dropdown-logout-btn');

// Login Welcome Banner Elements
const loginWelcomeBanner = document.getElementById('login-welcome-banner');
const welcomeBannerTitle = document.getElementById('welcome-banner-title');
const welcomeBannerSub   = document.getElementById('welcome-banner-sub');
const welcomeBannerClose = document.getElementById('welcome-banner-close');

function showAuthAlert(message, type = 'error') {
  if (!authAlert) return;
  authAlert.className = `auth-alert ${type}`;
  authAlert.textContent = message;
  authAlert.style.display = 'block';
}

function clearAuthAlert() {
  if (!authAlert) return;
  authAlert.style.display = 'none';
  authAlert.textContent = '';
}

function showAuthModal(view = 'login') {
  if (!authModalOverlay) return;
  clearAuthAlert();
  authModalOverlay.style.display = 'flex';

  // Toggle views
  const isAuthUser = Boolean(currentUser && (currentUser.emailVerified || isGoogleUser(currentUser)));
  if (authCloseBtn) {
    authCloseBtn.style.display = isAuthUser ? 'flex' : 'none';
  }

  if (view === 'login') {
    tabLogin.classList.add('active');
    tabRegister.classList.remove('active');
    document.getElementById('auth-tabs').style.display = 'flex';
    googleAuthContainer.style.display = 'block';
    loginForm.style.display = 'flex';
    registerForm.style.display = 'none';
    verificationView.style.display = 'none';
    forgotPwdForm.style.display = 'none';
    document.getElementById('auth-modal-title').textContent = 'Welcome to NOVA';
    document.getElementById('auth-modal-subtitle').textContent = 'Sign in or create an account to start using NOVA AI';
  } else if (view === 'register') {
    tabLogin.classList.remove('active');
    tabRegister.classList.add('active');
    document.getElementById('auth-tabs').style.display = 'flex';
    googleAuthContainer.style.display = 'block';
    loginForm.style.display = 'none';
    registerForm.style.display = 'flex';
    verificationView.style.display = 'none';
    forgotPwdForm.style.display = 'none';
    document.getElementById('auth-modal-title').textContent = 'Create NOVA Account';
    document.getElementById('auth-modal-subtitle').textContent = 'Sign up with email or Google to get started';
  } else if (view === 'verify') {
    document.getElementById('auth-tabs').style.display = 'none';
    googleAuthContainer.style.display = 'none';
    loginForm.style.display = 'none';
    registerForm.style.display = 'none';
    verificationView.style.display = 'block';
    forgotPwdForm.style.display = 'none';
    document.getElementById('auth-modal-title').textContent = 'Email Verification';
    document.getElementById('auth-modal-subtitle').textContent = 'Activate your NOVA AI account';
  } else if (view === 'forgot') {
    document.getElementById('auth-tabs').style.display = 'none';
    googleAuthContainer.style.display = 'none';
    loginForm.style.display = 'none';
    registerForm.style.display = 'none';
    verificationView.style.display = 'none';
    forgotPwdForm.style.display = 'flex';
    document.getElementById('auth-modal-title').textContent = 'Reset Password';
    document.getElementById('auth-modal-subtitle').textContent = 'Enter your email to receive a password reset link';
  }
}

function hideAuthModal() {
  if (!authModalOverlay) return;
  authModalOverlay.style.display = 'none';
}

function showVerificationScreen(email) {
  if (verifyEmailDisplay) {
    verifyEmailDisplay.textContent = email || 'your email address';
  }
  showAuthModal('verify');
}

function isGoogleUser(user) {
  if (!user || !user.providerData) return false;
  return user.providerData.some(p => p.providerId === 'google.com');
}

function showLoginWelcomeBanner(user, isGoogle = false) {
  if (!loginWelcomeBanner) return;
  const name = user.displayName || (user.email ? user.email.split('@')[0] : 'User');
  const method = isGoogle ? 'Google' : 'Email';

  const lang = (storage.getPreferences().language) || 'en';
  if (lang === 'te') {
    welcomeBannerTitle.textContent = `🎉 మీరు NOVA AI Assistant యాప్‌లోకి లాగిన్ అయ్యారు!`;
    welcomeBannerSub.textContent = `స్వాగతం ${name} (${method} ద్వారా విజయవంతంగా ప్రామాణీకరించబడింది).`;
  } else {
    welcomeBannerTitle.textContent = `🎉 You have logged in to NOVA AI Assistant!`;
    welcomeBannerSub.textContent = `Welcome, ${name}! (${method} Authentication verified).`;
  }

  loginWelcomeBanner.style.display = 'block';

  // Auto hide after 8 seconds
  setTimeout(() => {
    if (loginWelcomeBanner) {
      loginWelcomeBanner.style.display = 'none';
    }
  }, 8000);
}

function updateUserProfileUI(user) {
  currentUser = user;
  if (user) {
    const isVerified = user.emailVerified || isGoogleUser(user);
    const displayName = user.displayName || (user.email ? user.email.split('@')[0] : 'User');
    const email = user.email || '';
    const photoURL = user.photoURL;

    // Set Initials
    const initials = displayName ? displayName.charAt(0).toUpperCase() : 'U';

    if (photoURL && userAvatarImg) {
      userAvatarImg.src = photoURL;
      userAvatarImg.style.display = 'block';
      userAvatarInitials.style.display = 'none';
    } else {
      userAvatarImg.style.display = 'none';
      userAvatarInitials.textContent = initials;
      userAvatarInitials.style.display = 'block';
    }

    if (dropdownUserAvatar) {
      if (photoURL) {
        dropdownUserAvatar.innerHTML = `<img src="${photoURL}" alt="${displayName}" style="width:100%;height:100%;border-radius:50%;object-fit:cover;">`;
      } else {
        dropdownUserAvatar.textContent = initials;
      }
    }

    if (dropdownUserName) dropdownUserName.textContent = displayName;
    if (dropdownUserEmail) dropdownUserEmail.textContent = email;

    if (dropdownUserBadge) {
      dropdownUserBadge.style.display = 'inline-flex';
      if (isVerified) {
        dropdownBadgeText.textContent = isGoogleUser(user) ? 'Google Verified' : 'Verified Email';
        dropdownUserBadge.style.color = '#34d399';
        dropdownUserBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
      } else {
        dropdownBadgeText.textContent = 'Unverified Email';
        dropdownUserBadge.style.color = '#f87171';
        dropdownUserBadge.style.borderColor = 'rgba(239, 68, 68, 0.3)';
      }
    }

    if (dropdownAuthBtn) dropdownAuthBtn.style.display = 'none';
    if (dropdownLogoutBtn) dropdownLogoutBtn.style.display = 'flex';
  } else {
    // Guest state
    if (userAvatarImg) userAvatarImg.style.display = 'none';
    if (userAvatarInitials) {
      userAvatarInitials.textContent = '?';
      userAvatarInitials.style.display = 'block';
    }
    if (dropdownUserAvatar) dropdownUserAvatar.textContent = '?';
    if (dropdownUserName) dropdownUserName.textContent = 'Guest User';
    if (dropdownUserEmail) dropdownUserEmail.textContent = 'Sign in to save and sync chats';
    if (dropdownUserBadge) dropdownUserBadge.style.display = 'none';
    if (dropdownAuthBtn) {
      dropdownAuthBtn.style.display = 'flex';
      dropdownAuthBtnText.textContent = 'Sign In / Register';
    }
    if (dropdownLogoutBtn) dropdownLogoutBtn.style.display = 'none';
  }
}

// Attach Tab Listeners
if (tabLogin) tabLogin.addEventListener('click', () => showAuthModal('login'));
if (tabRegister) tabRegister.addEventListener('click', () => showAuthModal('register'));
if (forgotPwdLink) {
  forgotPwdLink.addEventListener('click', (e) => {
    e.preventDefault();
    showAuthModal('forgot');
  });
}
if (backToLoginBtn) {
  backToLoginBtn.addEventListener('click', () => showAuthModal('login'));
}
if (authCloseBtn) {
  authCloseBtn.addEventListener('click', () => {
    if (currentUser && (currentUser.emailVerified || isGoogleUser(currentUser))) {
      hideAuthModal();
    }
  });
}

// Password toggle eye buttons
document.querySelectorAll('.pwd-toggle-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const targetId = btn.dataset.target;
    const input = document.getElementById(targetId);
    if (input) {
      input.type = input.type === 'password' ? 'text' : 'password';
    }
  });
});

// Profile dropdown toggle
if (userAvatarBtn) {
  userAvatarBtn.addEventListener('click', (e) => {
    e.stopPropagation();
    if (userProfileDropdown) {
      const isShown = userProfileDropdown.style.display === 'block';
      userProfileDropdown.style.display = isShown ? 'none' : 'block';
    }
  });
}

// Close dropdown on click outside
document.addEventListener('click', (e) => {
  if (userProfileDropdown && !userProfileWrapper.contains(e.target)) {
    userProfileDropdown.style.display = 'none';
  }
});

// Dropdown Action Buttons
if (dropdownAuthBtn) {
  dropdownAuthBtn.addEventListener('click', () => {
    userProfileDropdown.style.display = 'none';
    showAuthModal('login');
  });
}

if (dropdownLogoutBtn) {
  dropdownLogoutBtn.addEventListener('click', async () => {
    userProfileDropdown.style.display = 'none';
    if (window.NovaAuth) {
      await window.NovaAuth.logoutUser();
    }
  });
}

if (welcomeBannerClose) {
  welcomeBannerClose.addEventListener('click', () => {
    if (loginWelcomeBanner) loginWelcomeBanner.style.display = 'none';
  });
}

// Google Sign In Handler
if (googleSignInBtn) {
  googleSignInBtn.addEventListener('click', async () => {
    clearAuthAlert();
    googleSignInBtn.disabled = true;
    googleSignInBtn.innerHTML = `<span>Signing in with Google...</span>`;

    const res = await window.NovaAuth.loginWithGoogle();
    googleSignInBtn.disabled = false;
    googleSignInBtn.innerHTML = `
      <svg class="google-icon" viewBox="0 0 24 24" width="20" height="20">
        <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
        <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
        <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
        <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
      </svg>
      <span>Continue with Google</span>
    `;

    if (res.success && res.user) {
      hideAuthModal();
      storage.setUser(res.user.uid);
      updateUserProfileUI(res.user);
      renderChatLists();
      startNewChat();
      showLoginWelcomeBanner(res.user, true);
    } else if (res.message) {
      showAuthAlert(res.message, 'error');
    }
  });
}

// Email Registration Form Handler
if (registerForm) {
  registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAuthAlert();

    const name = document.getElementById('reg-name').value.trim();
    const email = document.getElementById('reg-email').value.trim();
    const password = document.getElementById('reg-password').value;
    const confirmPassword = document.getElementById('reg-confirm-password').value;
    const submitBtn = document.getElementById('register-submit-btn');

    if (password !== confirmPassword) {
      showAuthAlert('Passwords do not match. Please verify.', 'error');
      return;
    }

    if (password.length < 6) {
      showAuthAlert('Password must be at least 6 characters.', 'error');
      return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>Creating account & sending link...</span>`;

    const res = await window.NovaAuth.registerWithEmail(email, password, name);
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Create Account & Send Verification</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;

    if (res.success && res.user) {
      storage.setUser(res.user.uid);
      updateUserProfileUI(res.user);
      showVerificationScreen(email);
    } else {
      showAuthAlert(res.message, 'error');
    }
  });
}

// Email Login Form Handler
if (loginForm) {
  loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAuthAlert();

    const email = document.getElementById('login-email').value.trim();
    const password = document.getElementById('login-password').value;
    const submitBtn = document.getElementById('login-submit-btn');

    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>Signing in...</span>`;

    const res = await window.NovaAuth.loginWithEmail(email, password);
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Sign In to NOVA</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>`;

    if (res.success && res.user) {
      storage.setUser(res.user.uid);
      updateUserProfileUI(res.user);

      if (!res.isVerified) {
        showVerificationScreen(email);
      } else {
        hideAuthModal();
        renderChatLists();
        showLoginWelcomeBanner(res.user, false);
      }
    } else {
      showAuthAlert(res.message, 'error');
    }
  });
}

// Check Email Verified Button Handler
if (checkVerifiedBtn) {
  checkVerifiedBtn.addEventListener('click', async () => {
    checkVerifiedBtn.disabled = true;
    checkVerifiedBtn.innerHTML = `<span>Checking verification status...</span>`;

    const isVerified = await window.NovaAuth.checkEmailVerified();
    checkVerifiedBtn.disabled = false;
    checkVerifiedBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="18" height="18"><polyline points="20 6 9 17 4 12"/></svg><span>I Have Verified My Email (Check Status)</span>`;

    if (isVerified) {
      hideAuthModal();
      const user = window.NovaAuth.getAuth()?.currentUser;
      if (user) {
        storage.setUser(user.uid);
        updateUserProfileUI(user);
        renderChatLists();
        startNewChat();
        showLoginWelcomeBanner(user, false);
      }
    } else {
      showAuthAlert('Email is not verified yet. Please open the link sent to your inbox, then click Check Status again.', 'error');
    }
  });
}

// Resend Email Verification Button Handler
if (resendEmailBtn) {
  resendEmailBtn.addEventListener('click', async () => {
    resendEmailBtn.disabled = true;
    if (resendBtnText) resendBtnText.textContent = 'Sending email...';

    const res = await window.NovaAuth.resendVerificationEmail();
    if (res.success) {
      showAuthAlert(res.message, 'success');
      let countdown = 60;
      const interval = setInterval(() => {
        countdown--;
        if (resendBtnText) resendBtnText.textContent = `Resend available in ${countdown}s`;
        if (countdown <= 0) {
          clearInterval(interval);
          resendEmailBtn.disabled = false;
          if (resendBtnText) resendBtnText.textContent = 'Resend Verification Email';
        }
      }, 1000);
    } else {
      resendEmailBtn.disabled = false;
      if (resendBtnText) resendBtnText.textContent = 'Resend Verification Email';
      showAuthAlert(res.message, 'error');
    }
  });
}

// Verification Screen Logout / Switch Account
if (verifyLogoutBtn) {
  verifyLogoutBtn.addEventListener('click', async () => {
    await window.NovaAuth.logoutUser();
    showAuthModal('login');
  });
}

// Forgot Password Form Handler
if (forgotPwdForm) {
  forgotPwdForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearAuthAlert();

    const email = document.getElementById('reset-email').value.trim();
    const submitBtn = document.getElementById('reset-submit-btn');

    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>Sending reset link...</span>`;

    const res = await window.NovaAuth.sendPasswordReset(email);
    submitBtn.disabled = false;
    submitBtn.innerHTML = `<span>Send Password Reset Link</span>`;

    if (res.success) {
      showAuthAlert(res.message, 'success');
    } else {
      showAuthAlert(res.message, 'error');
    }
  });
}

// ============================================================
// STANDARD UI EVENT LISTENERS
// ============================================================
themeToggleBtn.addEventListener('click', () => themeManager.toggle());

newChatBtn.addEventListener('click', () => {
  startNewChat();
  closeSidebar();
});

languageSelect.addEventListener('change', () => {
  const prefs = storage.getPreferences();
  prefs.language = languageSelect.value;
  storage.savePreferences(prefs);
});

imageUploadBtn.addEventListener('click', () => imageInput.click());
imageInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    await fileUploadManager.handleImageSelect(file);
    updateSendButtonState();
  }
  imageInput.value = '';
});

fileUploadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (file) {
    await fileUploadManager.handleFileSelect(file);
    updateSendButtonState();
  }
  fileInput.value = '';
});

document.querySelectorAll('.suggestion-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const prompt = chip.dataset.prompt;
    if (prompt) {
      userInput.value = prompt;
      updateSendButtonState();
      sendMessage();
    }
  });
});

// ============================================================
// APP INITIALIZATION & FIREBASE AUTH LIFECYCLE
// ============================================================
function initApp() {
  // Load preferences
  const prefs = storage.getPreferences();
  
  // Apply language
  if (prefs.language && languageSelect) {
    languageSelect.value = prefs.language;
  }
  
  // Apply TTS preference
  isTTSEnabled = prefs.ttsEnabled !== false;
  if (!isTTSEnabled && ttsToggle) {
    const onIcon = ttsToggle.querySelector('.tts-on-icon');
    const offIcon = ttsToggle.querySelector('.tts-off-icon');
    if (onIcon) onIcon.style.display = 'none';
    if (offIcon) offIcon.style.display = 'block';
  }

  // Set initial state
  setAppState(navigator.onLine ? 'READY' : 'OFFLINE');
  
  // Start mini holographic animation
  drawMiniHolo();
  
  // Focus input on desktop
  if (window.innerWidth > 768 && userInput) {
    userInput.focus();
  }

  // Initialize Firebase Auth Listener
  if (window.NovaAuth) {
    const auth = window.NovaAuth.getAuth();
    if (auth) {
      auth.onAuthStateChanged(async (user) => {
        if (user) {
          const verified = user.emailVerified || isGoogleUser(user);
          storage.setUser(user.uid);
          updateUserProfileUI(user);

          if (!verified) {
            showVerificationScreen(user.email);
          } else {
            hideAuthModal();
            renderChatLists();
            const curPrefs = storage.getPreferences();
            if (curPrefs.lastConversationId && storage.getConversation(curPrefs.lastConversationId)) {
              loadConversation(curPrefs.lastConversationId);
            } else {
              startNewChat();
            }
          }
        } else {
          // No user authenticated
          storage.setUser(null);
          updateUserProfileUI(null);
          renderChatLists();
          startNewChat();
          showAuthModal('login');
        }
      });
    } else {
      renderChatLists();
      startNewChat();
    }
  } else {
    renderChatLists();
    startNewChat();
  }
}

// Run initialization
initApp();

