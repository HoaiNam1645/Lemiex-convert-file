"""API Configuration"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# CORS settings
CORS_ORIGINS = ["*"]
CORS_CREDENTIALS = True
CORS_METHODS = ["*"]
CORS_HEADERS = ["*"]

# Server settings
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8009))

# File settings
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_EXTENSIONS = [".pes", ".dst", ".jef", ".exp", ".vp3", ".xxx", ".pec", ".hus", ".vip"]

# Processing settings
DEFAULT_PREVIEW_SIZE = 400
DEFAULT_MAX_SIZE = 800
DEFAULT_LINEWIDTH = 2
DOWNLOAD_TIMEOUT = 30.0

# Supported output formats
SUPPORTED_FORMATS = [".dst", ".pes", ".jef", ".exp", ".vp3", ".xxx", ".pec", ".hus", ".vip"]

# Backblaze B2 Configuration
B2_ACCESS_KEY_ID = os.getenv("B2_ACCESS_KEY_ID")
B2_SECRET_ACCESS_KEY = os.getenv("B2_SECRET_ACCESS_KEY")
B2_DEFAULT_REGION = os.getenv("B2_DEFAULT_REGION", "us-east-005")
B2_BUCKET = os.getenv("B2_BUCKET")
B2_ENDPOINT = os.getenv("B2_ENDPOINT")
B2_URL_CLOUD = os.getenv("B2_URL_CLOUD")

# Output paths on B2
B2_JSON_OUTPUT_PATH = os.getenv("B2_JSON_OUTPUT_PATH", "converted_json")
B2_DST_OUTPUT_PATH = os.getenv("B2_DST_OUTPUT_PATH", "converted_dst")
B2_LABEL_OUTPUT_PATH = os.getenv("B2_LABEL_OUTPUT_PATH", "converted_label")
B2_INFO_IMAGE_PATH = os.getenv("B2_INFO_IMAGE_PATH", "info_images")

# Callback API
BE_API_URL = os.getenv("BE_API_URL")
