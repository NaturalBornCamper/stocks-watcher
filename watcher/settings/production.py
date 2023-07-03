from watcher.settings.base import *
from watcher.utils import getenv

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS').split(',')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = getenv("DEBUG", False)

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         'NAME': getenv('DATABASE_NAME'),
#         'OPTIONS': {
#             'options': '-c search_path=app'
#         },
#         'USER': getenv('DATABASE_USER'),
#         'PASSWORD': getenv('DATABASE_PASSWORD'),
#         'HOST': getenv('DATABASE_HOST', 'localhost'),
#         'PORT': getenv('DATABASE_PORT', '5432'),
#     }
# }

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
