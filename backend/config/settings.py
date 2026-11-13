"""Django settings for the weather-aware truck routing API.

The project is stateless: there are no database models, so the auth/admin
apps and the database are left out entirely. Weather and geocoding responses
are cached in Django's local-memory cache instead.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_flag(name: str, default: bool) -> bool:
    """Read a boolean environment variable such as DJANGO_DEBUG=0."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: list[str]) -> list[str]:
    """Read a comma-separated environment variable into a list."""
    raw = os.environ.get(name)
    if not raw:
        return default
    return [item.strip() for item in raw.split(",") if item.strip()]


# Off unless asked for. Forgetting to set a variable then leaves a deployment
# safe, rather than showing stack traces to the public.
DEBUG = env_flag("DJANGO_DEBUG", False)

# A fixed development key is only acceptable while debugging locally. With
# DEBUG off, a missing key stops the server at start-up instead of letting it
# run in production signing data with a key that is published in this repo.
DEV_SECRET_KEY = "dev-only-insecure-key-never-use-in-production"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured(
            "DJANGO_SECRET_KEY is not set. Set it to a long random string, "
            "or set DJANGO_DEBUG=1 to run locally with the development key."
        )
    SECRET_KEY = DEV_SECRET_KEY

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# The Vite dev server runs on port 5173 and calls the API through its proxy.
# In production React is served by Django itself, so no cross-origin requests.
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", ["http://localhost:5173", "http://127.0.0.1:5173"]
)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "UNAUTHENTICATED_USER": None,
}

# Caching keeps us inside the public APIs' rate limits (Nominatim allows one
# request per second) and makes repeated searches fast.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "truck-routing",
        "TIMEOUT": 60 * 60,
        "OPTIONS": {"MAX_ENTRIES": 5000},
    }
}

# One line per planned trip, showing where the time went. Useful for
# explaining performance without reaching for a profiler.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "{levelname} {message}", "style": "{"}},
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "loggers": {
        "routing": {
            "handlers": ["console"],
            "level": os.environ.get("ROUTING_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
    },
}

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Where the built React app lands inside the Docker image. WhiteNoise serves
# this folder at the site root, so "/" gives index.html and "/assets/..."
# gives the bundles. In local development it does not exist, because Vite
# serves the frontend on its own port instead.
FRONTEND_DIST = BASE_DIR / "frontend_dist"
FRONTEND_INDEX = FRONTEND_DIST / "index.html"

if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST
    WHITENOISE_INDEX_FILE = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

if not DEBUG:
    # Pre-compressed copies of Django's own static files for the production
    # image. In development runserver serves them straight from disk.
    STORAGES = {
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
        },
    }
