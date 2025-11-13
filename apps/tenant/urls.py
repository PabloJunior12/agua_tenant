# apps/tenants/public_urls.py

from django.urls import path
from apps.tenant.views import  ClientViewSet, ValidateTenantView, ConecctMineco, ImportSiafApiView, MetasView, MetasImportCsvView
from rest_framework import routers

router = routers.DefaultRouter()

router.register("client", ClientViewSet)

urlpatterns = [

    path("connect/", ConecctMineco.as_view(), name="connect"),
    path('tenants/validate/<str:schema_name>/', ValidateTenantView.as_view()),
    path("import-siaf/", ImportSiafApiView.as_view(), name="import-siaf"),
    path("metas/", MetasView.as_view(), name="metas"),
    path("metas-import/", MetasImportCsvView.as_view(), name="generate-csv"),

] + router.urls
