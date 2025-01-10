from watcher.settings.base import *
from watcher.utils.helpers import getenv

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS').split(',')

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, "../static")
