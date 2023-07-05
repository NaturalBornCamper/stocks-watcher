from watcher.settings.base import *

from watcher.utils import getenv

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS', '127.0.0.1').split(',')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

STATIC_ROOT = os.path.join(BASE_DIR, "static")
