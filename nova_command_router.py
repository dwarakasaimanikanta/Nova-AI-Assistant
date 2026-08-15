import sys
import webbrowser
import subprocess

YOUTUBE_URL = "https://www.youtube.com"

def normalize(value):
    return value.strip().strip(" .,!?:;\"'").upper()

def execute_command(intent_line):
    parts = {}

    for item in intent_line.strip().split("|"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key.strip().upper()] = value.strip()

    intent = normalize(parts.get("INTENT", ""))
    target = normalize(parts.get("TARGET", ""))

    if intent == "OPEN" and target == "YOUTUBE":
        webbrowser.open(YOUTUBE_URL)
        return "SUCCESS: YouTube opened"

    if intent == "CLOSE" and target == "NOTEPAD":
        result = subprocess.run(
            ["taskkill", "/IM", "notepad.exe", "/F"],
            capture_output=True,
            text=True
        )

        if result.returncode == 0:
            return "SUCCESS: Notepad closed"

        return "FAILED: Notepad was not running"

    return f"REJECTED: Unsupported command INTENT={intent}, TARGET={target}"

if __name__ == "__main__":
    command = ""

    if len(sys.argv) >= 2:
        command = " ".join(sys.argv[1:])

    if not command and not sys.stdin.isatty():
        command = sys.stdin.read().strip()

    if not command:
        print("ERROR: No command received")
        raise SystemExit(1)

    print(execute_command(command))
