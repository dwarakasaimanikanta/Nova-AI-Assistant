"""
NOVA Dev Server Keep-Alive
Restarts vercel dev automatically whenever it exits.
Run: python server.py
"""
import subprocess, sys, time, os, signal

VERCEL = r"C:\Users\asus\AppData\Roaming\npm\node_modules\vercel\dist\index.js"
PORT   = 3000
CWD    = os.path.dirname(os.path.abspath(__file__))

MAX_RESTARTS   = 50      # give up after this many restarts
RESTART_DELAY  = 3       # seconds between restarts
MIN_UPTIME     = 5       # if server dies faster than this, count as a crash

proc = None

def start():
    return subprocess.Popen(
        ["node", VERCEL, "dev", "--listen", str(PORT)],
        cwd=CWD,
        stdout=sys.stdout,
        stderr=sys.stderr,
    )

def on_signal(sig, frame):
    print("\n[keeper] Shutting down...")
    if proc and proc.poll() is None:
        proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT,  on_signal)
signal.signal(signal.SIGTERM, on_signal)

print(f"[keeper] NOVA keep-alive wrapper — port {PORT}")
print(f"[keeper] Press Ctrl+C to stop.\n")

restarts = 0
while restarts < MAX_RESTARTS:
    t0 = time.time()
    print(f"[keeper] Starting server (attempt {restarts + 1})...")
    proc = start()
    proc.wait()
    uptime = time.time() - t0
    code   = proc.returncode
    print(f"\n[keeper] Server exited (code={code}, uptime={uptime:.1f}s)")

    if uptime < MIN_UPTIME:
        restarts += 1
        print(f"[keeper] Fast crash detected ({restarts}/{MAX_RESTARTS})")
    else:
        restarts = 0   # reset crash counter on healthy runs

    if restarts >= MAX_RESTARTS:
        print("[keeper] Too many fast crashes — stopping.")
        break

    print(f"[keeper] Restarting in {RESTART_DELAY}s...")
    time.sleep(RESTART_DELAY)

print("[keeper] Keep-alive exiting.")
