"""
config.py — Centralised settings & shared paths for Ghost Creator AI.
All modules import from here; secrets come from the .env file.
"""
import logging
import os
import shutil
import sys
import colorlog
from pathlib import Path
from dotenv import load_dotenv

# Release version — keep in sync with `installer_v4.iss` (MyAppVersion) and GUI/README branding.
APP_VERSION = "4.1"

# ── Load .env ──────────────────────────────────────────────────────────────────
load_dotenv()


def get_base_dir() -> Path:
    """
    Install / project root: folder containing the EXE when running a PyInstaller
    bundle; otherwise the directory containing this file. Use for writable paths
    (e.g. voiceover output) — never use sys._MEIPASS or __file__ alone for those.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


# ── Directory Layout ───────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).resolve().parent
OUTPUT_DIR  = BASE_DIR / "output"
TEMP_DIR    = BASE_DIR / "temp"
OUTPUT_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)


def _bundle_root() -> Path:
    """PyInstaller extract dir when frozen; project root when running from source."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return BASE_DIR


def _ffmpeg_exe_names() -> tuple[str, str]:
    if sys.platform == "win32":
        return "ffmpeg.exe", "ffprobe.exe"
    return "ffmpeg", "ffprobe"


def get_ffmpeg_executable() -> str:
    """
    Path to ffmpeg: bundled ``ffmpeg/`` next to the app, then PATH, then bare name.

    ``modules/voicer.py`` used to resolve ``modules/ffmpeg/`` (wrong); callers must
    use this so one-folder installs and PyInstaller bundles both work.
    """
    ff, _ = _ffmpeg_exe_names()
    bundled = _bundle_root() / "ffmpeg" / ff
    if bundled.exists():
        return str(bundled)
    w = shutil.which("ffmpeg")
    if w:
        return w
    return ff


def get_ffprobe_executable() -> str:
    """Path to ffprobe: bundled folder, then PATH, then bare name."""
    _, fp = _ffmpeg_exe_names()
    bundled = _bundle_root() / "ffmpeg" / fp
    if bundled.exists():
        return str(bundled)
    w = shutil.which("ffprobe")
    if w:
        return w
    return fp


# ── API Keys ───────────────────────────────────────────────────────────────────
GEMINI_API_KEY      = os.getenv("GEMINI_API_KEY", "")

# ── YouTube / Playwright ───────────────────────────────────────────────────────
YT_PROFILE_DIR  = os.getenv("YT_PROFILE_DIR", "")
YT_PROFILE_NAME = os.getenv("YT_PROFILE_NAME", "Default")

# ── Video Settings ─────────────────────────────────────────────────────────────
VIDEO_WIDTH  = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS    = 30

# ── Gemini Model ───────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-2.0-flash"

# ── Language Settings ──────────────────────────────────────────────────────────
# Voiceover language for the script (e.g. 'hindi', 'english', 'hinglish')
# Image prompts are ALWAYS generated in English for best results.
VOICEOVER_LANG = os.getenv("VOICEOVER_LANG", "hindi")

# ── Default Topics (used when Google Trends + RSS both fail) ──────────────
DEFAULT_TOPICS = [
    "Simple Morning Habits That Make Your Day Easier",
    "How to Sleep Better Tonight (Science-Backed Tips)",
    "Small Money Habits That Add Up Over Time",
    "Easy Meal Prep Ideas for Busy Weekdays",
    "Why We Procrastinate and One Trick to Start Anyway",
    "How to Stay Focused When Your Phone Keeps Buzzing",
    "Quick Home Workouts When You Have No Gym",
    "Healthy Snack Swaps You Won't Hate",
    "How to Save Time on Chores Every Week",
    "Simple Ways to Feel Less Stressed in 5 Minutes",
    "What to Drink Before Coffee for More Energy",
    "How to Talk About Money Without a Fight",
    "Why Taking Short Walks Actually Helps Your Brain",
    "How to Remember Names and Stop Forgetting Them",
    "One-Minute Desk Stretches for Back and Neck",
    "How to Plan Your Week in 15 Minutes",
    "Easy Ways to Cut Down Screen Time Before Bed",
    "Why Drinking More Water Changes Your Day",
    "How to Learn Something New With 10 Minutes a Day",
    "Small Kind Habits That Make People Like You More",
]

# ── Logging ────────────────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """Return a colourised, formatted logger for any module."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s[%(asctime)s] %(levelname)-8s%(reset)s %(cyan)s%(name)s%(reset)s › %(message)s",
        datefmt="%H:%M:%S",
        log_colors={
            "DEBUG":    "white",
            "INFO":     "green",
            "WARNING":  "yellow",
            "ERROR":    "red",
            "CRITICAL": "bold_red",
        }
    ))
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger
