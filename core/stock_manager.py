import urllib.request
import threading
from pathlib import Path
from config import get_logger, get_writable_path

log = get_logger("stock_manager")

STOCK_ASSETS_DIR = get_writable_path("assets/stock")
MUSIC_DIR = STOCK_ASSETS_DIR / "music"
SFX_DIR = STOCK_ASSETS_DIR / "sfx"

STOCK_MUSIC = {
    "lofi_cafe_ambient.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3",
    "cinematic_horizon.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3",
    "acoustic_sunset.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3",
    "neon_techno_synth.mp3": "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-4.mp3"
}

STOCK_SFX = {
    "button_click.mp3": "https://www.soundjay.com/buttons/sounds/button-1.mp3",
    "whoosh_swoosh.mp3": "https://www.soundjay.com/button/sounds/button-3.mp3",
    "page_turn.mp3": "https://www.soundjay.com/misc/sounds/page-turn-1.mp3",
    "camera_shutter.mp3": "https://www.soundjay.com/mechanical/sounds/camera-shutter-click-01.mp3"
}

def ensure_stock_assets():
    """Verify and download stock music and sfx files asynchronously."""
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)
    SFX_DIR.mkdir(parents=True, exist_ok=True)

    def download_loop():
        # Music Downloads
        for filename, url in STOCK_MUSIC.items():
            dest = MUSIC_DIR / filename
            if not dest.is_file() or dest.stat().st_size < 1000:
                log.info(f"Downloading stock music: {filename} ...")
                try:
                    urllib.request.urlretrieve(url, str(dest.resolve()))
                    log.info(f"Successfully downloaded {filename}")
                except Exception as e:
                    log.warning(f"Failed to download stock music {filename}: {e}")

        # SFX Downloads
        for filename, url in STOCK_SFX.items():
            dest = SFX_DIR / filename
            if not dest.is_file() or dest.stat().st_size < 100:
                log.info(f"Downloading stock SFX: {filename} ...")
                try:
                    urllib.request.urlretrieve(url, str(dest.resolve()))
                    log.info(f"Successfully downloaded {filename}")
                except Exception as e:
                    log.warning(f"Failed to download stock SFX {filename}: {e}")

    # Run in a background thread to prevent blocking Uvicorn startup
    thread = threading.Thread(target=download_loop, name="stock_downloader")
    thread.daemon = True
    thread.start()
