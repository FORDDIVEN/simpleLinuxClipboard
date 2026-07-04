import os
from pathlib import Path


APP_NAME = "winvclipboard"
MAX_HISTORY_ITEMS = 50

DATA_DIR = Path(
    os.environ.get("WINVCLIPBOARD_DATA_DIR", Path.home() / ".local" / "share" / APP_NAME)
)
CACHE_DIR = Path(os.environ.get("WINVCLIPBOARD_CACHE_DIR", Path.home() / ".cache" / APP_NAME))
HISTORY_FILE = DATA_DIR / "history.json"
SETTINGS_FILE = DATA_DIR / "settings.json"

SUPPORTED_TYPES = {"text", "image"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
