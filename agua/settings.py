from pathlib import Path
import os


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
    # Primero detectamos el tenant por subcarpeta
    "apps.tenant.middleware.tenant_subfolder_middleware.TenantSubfolderMiddleware",

    # Luego django-tenants activa el schema
    # "django_tenants.middleware.main.TenantMainMiddleware",

    # Ahora sí podemos asignar user_model dinámico
    # "apps.tenants.middleware.auth_user_middleware.DynamicAuthUserMiddleware",
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

# -----------------------------------
# REST FRAMEWORK
# -----------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.TokenAuthentication",
    ),
    "EXCEPTION_HANDLER": "apps.agua.core.exceptions.custom_exception_handler",
}

WSGI_APPLICATION = "agua.wsgi.application"

# -----------------------------------
# DATABASE
# -----------------------------------
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

# -----------------------------------
# AUTH USER MODEL
# -----------------------------------
# Valor por defecto → se cambiará dinámicamente en el middleware
AUTH_USER_MODEL = "user.User"
# AUTH_USER_MODEL = "user.User"

# -----------------------------------
# OTROS
# -----------------------------------
X_FRAME_OPTIONS = "ALLOWALL"

LANGUAGE_CODE = "es"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True
USE_L10N = False

CORS_ALLOWED_ORIGINS = [
    "http://demo.localhost:4200",
    "http://pangoa.localhost:4200",
    "http://localhost:4200",
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
