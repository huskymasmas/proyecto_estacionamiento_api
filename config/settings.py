import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-key")
DEBUG = True
ALLOWED_HOSTS = ["*"]

# Sin modelos ni migraciones: solo se usan consultas SQL directas
INSTALLED_APPS = [
    "corsheaders",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # debe ir primero
    "django.middleware.common.CommonMiddleware",
]

# Permite que el index.html abierto desde file:// consuma la API
CORS_ALLOW_ALL_ORIGINS = True

ROOT_URLCONF = "config.urls"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "estacionamiento_db"),
        "USER": os.environ.get("DB_USER", ""),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_SERVER", "localhost"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            # RDS corre en UTC; Guatemala es UTC-6 todo el año (sin horario de verano)
            "init_command": "SET time_zone = '-06:00'",
        },
    }
}

# La BD guarda DATETIME "naive" con la hora local de Guatemala (la sesión MySQL usa UTC-6)
USE_TZ = False
TIME_ZONE = "America/Guatemala"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
