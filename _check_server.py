"""
Helper for bat files: check Chatterbox TTS, auto-start if needed.
Usage:
  python _check_server.py check    -> exit 0 if online, exit 1 if offline
  python _check_server.py start    -> start server if not running, wait until online
"""
import sys
import os
import subprocess
import time
import urllib.request
import urllib.error

URL = "http://127.0.0.1:8004/"
TIMEOUT = 5


def is_online():
    try:
        urllib.request.urlopen(URL, timeout=TIMEOUT)
        return True
    except urllib.error.HTTPError:
        return True  # server responded, just not 200 — still alive
    except Exception:
        return False


def start_and_wait():
    if is_online():
        print("[OK] Chatterbox TTS already running!")
        return 0

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cb_dir = os.path.join(script_dir, "Chatterbox-TTS-Server-windows-easyInstallation")
    win_run = os.path.join(cb_dir, "win-run.bat")

    if not os.path.exists(win_run):
        print("[ERROR] Chatterbox server not found!")
        print(f"        Expected: {win_run}")
        return 1

    print("[*] Starting Chatterbox TTS server...")
    subprocess.Popen(
        ["cmd", "/c", "start", "Chatterbox TTS", "/min", win_run],
        cwd=cb_dir,
        shell=False,
    )

    print("[*] Waiting for server to load (this can take 30-60 seconds)...")
    for i in range(60):
        time.sleep(2)
        if is_online():
            print("[OK] Chatterbox TTS server is online!")
            return 0

    print("[WARNING] Server did not respond after 120 seconds.")
    print("          Check the Chatterbox window in the taskbar.")
    return 2


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "check":
        sys.exit(0 if is_online() else 1)
    elif cmd == "start":
        sys.exit(start_and_wait())
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
