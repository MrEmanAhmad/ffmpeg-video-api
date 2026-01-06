"""
Centralized configuration for FFmpeg Video API
"""
import os
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).parent
TEMPLATES_DIR = BASE_DIR / "templates"
TEMP_DIR = Path(os.getenv("TEMP_DIR", "/tmp/videos"))

# Ensure directories exist
TEMPLATES_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Server configuration
PORT = int(os.getenv("PORT", "10000"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Job queue settings
MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_JOBS", "2"))
MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "10"))

# Video settings
MAX_VIDEO_DURATION = int(os.getenv("MAX_VIDEO_DURATION", "120"))  # seconds
MAX_VIDEO_SIZE_MB = int(os.getenv("MAX_VIDEO_SIZE_MB", "100"))
VIDEO_RETENTION_HOURS = int(os.getenv("VIDEO_RETENTION_HOURS", "24"))

# Image download settings
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv("IMAGE_DOWNLOAD_TIMEOUT", "30"))  # seconds
ALLOWED_DOMAINS = [d.strip() for d in os.getenv("ALLOWED_DOMAINS", "").split(",") if d.strip()]

# API Key Authentication
# Comma-separated list of valid API keys (empty = no auth required)
API_KEYS = [k.strip() for k in os.getenv("API_KEYS", "").split(",") if k.strip()]
AUTH_ENABLED = len(API_KEYS) > 0

# Webhook settings
WEBHOOK_TIMEOUT = int(os.getenv("WEBHOOK_TIMEOUT", "10"))  # seconds
WEBHOOK_RETRIES = int(os.getenv("WEBHOOK_RETRIES", "3"))

# Default video output settings
DEFAULT_OUTPUT_SETTINGS = {
    "width": 720,
    "height": 1280,
    "fps": 30,
    "format": "mp4",
    "codec": "libx264"
}

# Default audio settings
DEFAULT_AUDIO_SETTINGS = {
    "volume": 1.0,
    "fade_in": 0,
    "fade_out": 0,
    "loop": True
}

