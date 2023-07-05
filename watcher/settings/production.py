import os
import sys
from pathlib import Path
with open("bob.txt", 'a') as f: f.write(f"Working directory: {os.getcwd()}\n")
# sys.path.append(Path(__file__).resolve().parent)
# sys.path.append(Path(__file__).resolve().parent.parent)
# sys.path.append(Path(__file__).resolve().parent.parent.parent)

for pat in sys.path:
    with open("bob.txt", 'a') as f: f.write(f"path: {pat}\n")

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
