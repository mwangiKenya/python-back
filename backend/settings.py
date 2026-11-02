"""
Django settings for backend project.

All secrets and database details come from environment variables:
  - locally: the .env file next to manage.py
  - on Render: the Environment tab in the dashboard
To run a command against Supabase from your computer, set ENV_FILE=.env.supabase
for that command only (its values override the ones in .env).
"""
import os
from pathlib import Path

from decouple import Config, RepositoryEnv, Csv, undefined
from decouple import config as _base_config

BASE_DIR = Path(__file__).resolve().parent.parent


# =============================================================
# ENVIRONMENT LOADING
# =============================================================
# .env (or real environment variables) is always read.
# If ENV_FILE is set (e.g. .env.supabase), values in that file take priority.
_override = None
_override_name = os.environ.get("ENV_FILE")
if _override_name:
    _override = Config(RepositoryEnv(BASE_DIR / _override_name))


def env(key, default=undefined, cast=undefined):
    if _override is not None and key in _override.repository.data:
        return _override(key, cast=cast)
    return _base_config(key, default=default, cast=cast)


# =============================================================
# CORE
# =============================================================
SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG", default=False, cast=bool)
ALLOWED_HOSTS = env(
    "ALLOWED_HOSTS",
    default="localhost,127.0.0.1,.onrender.com",
    cast=Csv(),
)

ROOT_URLCONF = "backend.urls"
WSGI_APPLICATION = "backend.wsgi.application"


# =============================================================
# APPLICATIONS
# =============================================================
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "api",
    "readings",
    "billings",
    "users",
]


# =============================================================
# MIDDLEWARE
# =============================================================
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# =============================================================
# CORS
# =============================================================
CORS_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "https://mwangikenya.github.io",
]
CORS_ALLOW_CREDENTIALS = True


# =============================================================
# TEMPLATES
# =============================================================
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# =============================================================
# DATABASE
# =============================================================
# Local:    DB_HOST=localhost, DB_PORT=5432
# Supabase: pooler host. Use port 5432 (session mode) when running migrations
#           from your computer, and 6543 (transaction mode) on Render.
# No defaults for NAME/USER/PASSWORD/HOST on purpose: if one is missing,
# Django fails loudly instead of connecting to the wrong database.
DB_HOST = env("DB_HOST")
DB_PORT = env("DB_PORT", default="5432")
_local_db = DB_HOST in ("localhost", "127.0.0.1")

_db_options = {"connect_timeout": 5}
if not _local_db:
    _db_options["sslmode"] = "require"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": DB_HOST,
        "PORT": DB_PORT,
        "OPTIONS": _db_options,
        "CONN_MAX_AGE": 0,
        # Required when going through Supabase's transaction pooler (port 6543)
        "DISABLE_SERVER_SIDE_CURSORS": DB_PORT == "6543",
    }
}


# =============================================================
# AUTHENTICATION / REST FRAMEWORK
# =============================================================
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
}


# =============================================================
# INTERNATIONALIZATION
# =============================================================
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# =============================================================
# STATIC FILES
# =============================================================
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")


# =============================================================
# SMS PROVIDERS
# =============================================================
# Advanta (live)
ADVANTA_API_URL = env(
    "ADVANTA_API_URL",
    default="https://quicksms.advantasms.com/api/services/sendbulk",
)
ADVANTA_PARTNER_ID = env("ADVANTA_PARTNER_ID")
ADVANTA_API_KEY = env("ADVANTA_API_KEY")
ADVANTA_SHORTCODE = env("ADVANTA_SHORTCODE")

# Africa's Talking (sandbox)
AT_USERNAME = env("AT_USERNAME", default="sandbox")
AT_API_KEY = env("AT_API_KEY", default="")
AT_SENDER_ID = env("AT_SENDER_ID", default=None)