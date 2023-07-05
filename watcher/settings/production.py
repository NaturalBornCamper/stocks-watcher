import os
import sys

from watcher.settings.base import *
from watcher.utils import getenv

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS').split(',')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = getenv("DEBUG", False)


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, "../static")
