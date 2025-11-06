from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from django.conf.urls.static import static

urlpatterns = [
    # Admin (tenant principal)
    path('admin/', admin.site.urls),

    # Rutas de usuarios públicas (login, registro, etc.)
    path('user/', include('apps.user.urls')),

    # Endpoints públicos de tu API
    path('api/', include('apps.tenant.urls')),

    # Endpoints de tenants usando subcarpeta
    path('clientes/<str:tenant_name>/api/', include('apps.agua.urls')),
]

# Archivos media

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
