"""
Configuration file for BoxChat application
"""
import json
import os

# Try to load configuration from `config.json` located next to this file.
# If the file is missing or a key is absent, fall back to the defaults below.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_JSON_PATH = os.path.join(_BASE_DIR, 'config.json')

# Defaults
_defaults = {
    'SQLALCHEMY_DATABASE_URI': 'sqlite:///thecomboxmsgr.db',
    'SQLALCHEMY_TRACK_MODIFICATIONS': False,
    'SECRET_KEY': 'super_secret_key_v2',
    'UPLOAD_FOLDER': 'uploads',
    'MAX_CONTENT_LENGTH': 50 * 1024 * 1024,
    'ALLOWED_EXTENSIONS': [
        'png', 'jpg', 'jpeg', 'gif', 'webp',
        'mp3', 'ogg', 'flac', 'wav', 'midi', 'mid',
        'mp4', 'webm', 'mov', 'avi', 'mkv',
        'txt', 'py', 'js', 'html', 'css', 'json', 'xml', 'md', 'pdf', 'zip', 'rar'
    ],
    'IMAGE_EXTENSIONS': ['png', 'jpg', 'jpeg', 'gif', 'webp'],
    'MUSIC_EXTENSIONS': ['mp3', 'ogg', 'flac', 'wav'],
    'VIDEO_EXTENSIONS': ['mp4', 'webm', 'mov', 'avi', 'mkv'],
    'UPLOAD_SUBDIRS': {
        'avatars': 'avatars',
        'room_avatars': 'room_avatars',
        'channel_icons': 'channel_icons',
        'files': 'files',
        'music': 'music',
        'videos': 'videos'
    }
}

_cfg = {}
try:
    with open(_JSON_PATH, 'r', encoding='utf-8') as f:
        _cfg = json.load(f) or {}
except FileNotFoundError:
    # No config.json present — we'll use defaults
    _cfg = {}
except Exception:
    # If parsing fails, fall back to defaults but continue (app may log/notify)
    _cfg = {}

# Helper to get value from JSON or defaults
def _get(key):
    return _cfg.get(key, _defaults.get(key))

# Database
SQLALCHEMY_DATABASE_URI = _get('SQLALCHEMY_DATABASE_URI')
SQLALCHEMY_TRACK_MODIFICATIONS = _get('SQLALCHEMY_TRACK_MODIFICATIONS')

# Security
SECRET_KEY = _get('SECRET_KEY')

# File uploads
UPLOAD_FOLDER = _get('UPLOAD_FOLDER')
MAX_CONTENT_LENGTH = int(_get('MAX_CONTENT_LENGTH'))

# Allowed file extensions (store as sets in runtime for quick membership checks)
ALLOWED_EXTENSIONS = set(_get('ALLOWED_EXTENSIONS') or [])

# File type groups
IMAGE_EXTENSIONS = set(_get('IMAGE_EXTENSIONS') or [])
MUSIC_EXTENSIONS = set(_get('MUSIC_EXTENSIONS') or [])
VIDEO_EXTENSIONS = set(_get('VIDEO_EXTENSIONS') or [])

# Upload subdirectories (relative names only)
UPLOAD_SUBDIRS = dict(_get('UPLOAD_SUBDIRS') or {})


def init_upload_folders():
    """Create upload directories if they don't exist"""
    base = UPLOAD_FOLDER
    os.makedirs(base, exist_ok=True)
    for subdir in UPLOAD_SUBDIRS.values():
        path = os.path.join(base, subdir)
        os.makedirs(path, exist_ok=True)
