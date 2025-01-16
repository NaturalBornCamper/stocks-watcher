from settings.base import *

ALLOWED_HOSTS = getenv('ALLOWED_HOSTS', '127.0.0.1').split(',')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = getenv("DEBUG", True)

# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LOGGING = {
    'version': 1,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': 'django_queries.log',
        },
    },
    'loggers': {
        'django.db.backends': {
            # 'handlers': ['console', 'file'],
            'handlers': ['file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# LOGGING = {
#     "version": 1,
#     "disable_existing_loggers": False,
#     "formatters": {
#         "verbose": {
#             "format": "{asctime} [{module}:{levelname}] {message}",
#             "style": "{",
#         },
#         "simple": {
#             "format": "[{module}:{levelname}] {message}",
#             "style": "{",
#         },
#     },
#     "filters": {
#         "require_debug_true": {
#             "()": "django.utils.log.RequireDebugTrue",
#         },
#     },
#     "handlers": {
#         "console": {
#             "level": "INFO",
#             "filters": ["require_debug_true"],
#             "class": "logging.StreamHandler",
#             "formatter": "simple",
#         },
#         "mail_admins": {
#             "level": "ERROR",
#             "class": "django.utils.log.AdminEmailHandler",
#             "filters": ["special"],
#         },
#     },
#     "loggers": {
#         "django": {
#             "handlers": ["console"],
#             "propagate": True,
#         },
#         "myproject.custom": {
#             "handlers": ["console", "mail_admins"],
#             "level": "INFO",
#             "filters": ["special"],
#         },
#     },
# }
