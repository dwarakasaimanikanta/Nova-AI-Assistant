"""
remove_nova_startup.py
----------------------
Removes Nova from Windows Startup by unlinking the per-user Startup shortcut.
Does NOT require administrator privileges.
"""

import os
import sys
from pathlib import Path

def main():
    print("Removing Nova from Windows Startup...")
    
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("[ERROR] APPDATA environment variable not found. Cannot resolve Startup directory.")
        sys.exit(1)
        
    startup_dir = Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    shortcut_path = startup_dir / "NovaAIAssistant.lnk"
    
    if shortcut_path.exists():
        try:
            shortcut_path.unlink()
            print("[SUCCESS] Successfully removed Nova from Windows Startup.")
        except Exception as e:
            print(f"[ERROR] Failed to delete shortcut file at {shortcut_path}: {e}")
            sys.exit(1)
    else:
        print("[INFO] No Nova startup entry was found. Nothing to remove.")

if __name__ == "__main__":
    main()
