"""Constants for the Samsung Frame TV Art Changer integration."""

DOMAIN = "samsung_frame_art"

MANUFACTURER = "samsung-frametv-artchanger"

CONF_TV_IPS = "tv"
CONF_AUTOMATION_TOKEN = "automation_token"
CONF_MEDIA_DIR = "media_dir"

DEFAULT_REFRESH_SECONDS = 30
DEFAULT_SNAPSHOT_TTL_SECONDS = 20
DEFAULT_MEDIA_SUBDIR = "frame_art"

PANEL_URL_PATH = DOMAIN
PANEL_TITLE = "Frame Art"
PANEL_ICON = "mdi:image-multiple"

# Upload/scan formats. Pillow handles jpg/png/webp/gif/bmp/tiff/avif natively;
# heic/heif require pillow-heif (declared in manifest.json requirements).
SUPPORTED_UPLOAD_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".avif",
}

SLIDESHOW_MIN_INTERVAL_SECONDS = 5
SLIDESHOW_MAX_INTERVAL_SECONDS = 86400  # 24 hours
SLIDESHOW_DEFAULT_INTERVAL_SECONDS = 3600  # 1 hour
SLIDESHOW_MAX_CONSECUTIVE_FAILURES = 10
