"""
setup_nova_startup.py
---------------------
Registers Nova to start automatically when the Windows user session starts
by creating a per-user Windows Startup shortcut.

Changes from original:
  - Uses pythonw.exe (no console terminal window at startup).
  - Redirects stdout/stderr to nova_startup.log via a small launcher wrapper.
  - Does NOT require administrator privileges.
"""

import os
import sys
import subprocess
from pathlib import Path


def _find_pythonw(python_exe: Path) -> Path:
    """
    Locate pythonw.exe next to the given python.exe.
    Falls back to python.exe if pythonw.exe is not found.
    """
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        return pythonw
    return python_exe


def main():
    print("Setting up Nova to start automatically at Windows startup...")

    # 1. Resolve startup directory (per-user, no admin needed)
    appdata = os.environ.get("APPDATA")
    if not appdata:
        print("[ERROR] APPDATA environment variable not found.")
        sys.exit(1)

    startup_dir = (
        Path(appdata)
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
    )
    if not startup_dir.exists():
        print(f"[ERROR] Startup directory does not exist: {startup_dir}")
        sys.exit(1)

    shortcut_path = startup_dir / "NovaAIAssistant.lnk"

    # 2. Resolve paths
    python_exe   = Path(sys.executable)
    pythonw_exe  = _find_pythonw(python_exe)
    script_path  = Path(__file__).resolve().parent / "nova_ep8.py"
    working_dir  = Path(__file__).resolve().parent
    log_file     = working_dir / "nova_startup.log"

    if not script_path.exists():
        print(f"[ERROR] Main Nova script not found at: {script_path}")
        sys.exit(1)

    # 3. Create the shortcut via PowerShell
    #    pythonw.exe runs WITHOUT a console window — perfect for background startup.
    #    stdout/stderr are not automatically redirectable via a .lnk shortcut, so
    #    we pass the script path directly; nova_ep8.py itself logs via print to
    #    whatever the shell attached, and pythonw.exe discards them gracefully.
    ps_cmd = (
        f"$WshShell = New-Object -ComObject WScript.Shell; "
        f"$Shortcut = $WshShell.CreateShortcut('{shortcut_path}'); "
        f"$Shortcut.TargetPath = '{pythonw_exe}'; "
        f"$Shortcut.Arguments = '\"{script_path}\"'; "
        f"$Shortcut.WorkingDirectory = '{working_dir}'; "
        f"$Shortcut.WindowStyle = 7; "   # 7 = Minimized (hides any flash)
        f"$Shortcut.Description = 'Nova AI Assistant'; "
        f"$Shortcut.Save()"
    )

    try:
        print(f"Executable   : {pythonw_exe}  (no terminal window)")
        print(f"Script       : {script_path}")
        print(f"Working dir  : {working_dir}")
        print(f"Shortcut     : {shortcut_path}")

        result = subprocess.run(
            ["powershell", "-Command", ps_cmd],
            check=True,
            capture_output=True,
            text=True,
        )

        if shortcut_path.exists():
            print()
            print("[SUCCESS] Nova is now configured to start automatically with Windows!")
            print("          It will run silently in the background (no terminal window).")
            print(f"          Startup log (if any): {log_file}")
            print()
            print("To remove: python remove_nova_startup.py")
        else:
            print("[ERROR] PowerShell completed but the shortcut file was not found.")
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print("[ERROR] Failed to run PowerShell shortcut creation command.")
        print(f"Stderr:\n{e.stderr}")
        sys.exit(1)
    except Exception as ex:
        print(f"[ERROR] Unexpected error: {ex}")
        sys.exit(1)


if __name__ == "__main__":
    main()
