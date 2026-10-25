import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR))).resolve()
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(DATA_DIR / "temp_uploads"))).resolve()
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))  # 100 MiB
TTL_SECONDS = 600
CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "15"))
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ALLOWED_EXTENSIONS_RAW = os.getenv("ALLOWED_EXTENSIONS", "")
ALLOWED_EXTENSIONS = {
    ext.strip().lower().lstrip(".")
    for ext in ALLOWED_EXTENSIONS_RAW.split(",")
    if ext.strip()
}
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
