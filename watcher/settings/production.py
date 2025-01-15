import os

from watcher.settings.base import *
from watcher.utils.helpers import getenv

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS').split(',')

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Root www folder on the server
STATIC_ROOT = getenv('STATIC_ROOT', BASE_DIR / "static")
