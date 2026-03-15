from pathlib import Path
import os
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-uma#1&pshedj#xh1(hbzy%z9n)hfr1%7ec11j(3v=7sk7)b&4='
DEBUG = True
ALLOWED_HOSTS = ["*"]

# -----------------------------------
# APPS
# -----------------------------------
SHARED_APPS = [

    'django_tenants',
    'apps.tenant',
    'apps.user',      
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles', 
    'django.contrib.admin', # admin solo en tenant
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',

]

TENANT_APPS = [
        
    'apps.agua',
               
]

INSTALLED_APPS = list(SHARED_APPS) + [app for app in TENANT_APPS if app not in SHARED_APPS]

TENANT_MODEL = "tenant.Client"
TENANT_DOMAIN_MODEL = "tenant.Domain"

DATABASE_ROUTERS = ('django_tenants.routers.TenantSyncRouter',)

TENANT_SUBFOLDER_PREFIX = "clientes"
SHOW_PUBLIC_IF_NO_TENANT_FOUND = False

# -----------------------------------
# MIDDLEWARE
# -----------------------------------

MIDDLEWARE = [
    "apps.tenant.middleware.tenant_subfolder_middleware.TenantSubfolderMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = 'agua.urls'

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "EXCEPTION_HANDLER": "apps.agua.core.exceptions.custom_exception_handler",
}

WSGI_APPLICATION = "agua.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": "agua_tenant",
        "USER": "postgres",
        "PASSWORD": "curo",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=59),   # ✔️ ideal ERP
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=12),    # o 1 día
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
 
AUTH_USER_MODEL = "user.User"

X_FRAME_OPTIONS = "ALLOWALL"

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True
USE_L10N = False

CORS_ALLOWED_ORIGINS = [
    "http://demo.localhost:4200",
    "http://pangoa.localhost:4200",
    "http://sanmarcos.localhost:4200",
    "http://localhost:4200",
    "https://ugm.pe"
]

CORS_ALLOW_CREDENTIALS = True

CSRF_TRUSTED_ORIGINS = [
    "https://api.ugm.pe",
]

STATIC_URL = "/static/"
STATICFILES_DIRS = [os.path.join(BASE_DIR, "static")]
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# if os.name == "nt":  # Windows

BACKUP_GLOBAL_PATH = BASE_DIR / "backups" / "global"

# else:  # Linux

BACKUP_TENANT_PATH = BASE_DIR / "backups" / "tenants"

MP_ACCESS_TOKEN="APP_USR-5776140338113863-121820-5485b8aea2d65b5c59e79ff2bff8526c-3078421227"
MP_WEBHOOK_URL="https://api.ugm.pe/api/webhooks/mercadopago/"