# apps/tenants/public_urls.py

from django.urls import path
from apps.tenant.views import  ClientViewSet, ReceiptBatchViewSet, MercadoPagoWebhookView, TenantBackupDownloadView, TenantBackupView, GlobalBackupView, GlobalBackupDownloadView, ValidateTenantView, ConecctMineco, ImportSiafApiView, MetasView, MetasImportCsvView
from rest_framework import routers

router = routers.DefaultRouter()

router.register("client", ClientViewSet)
router.register("receipt-batch", ReceiptBatchViewSet)


urlpatterns = [

    path("connect/", ConecctMineco.as_view(), name="connect"),
    path('tenants/validate/<str:schema_name>/', ValidateTenantView.as_view()),
    path("import-siaf/", ImportSiafApiView.as_view(), name="import-siaf"),
    path("metas/", MetasView.as_view(), name="metas"),
    path("metas-import/", MetasImportCsvView.as_view(), name="generate-csv"),
    path("global/", GlobalBackupView.as_view()),
    path("global/<int:backup_id>/download/", GlobalBackupDownloadView.as_view()),
    path("tenant-backup/<int:tenant_id>/", TenantBackupView.as_view()),
    path("tenant-backup/<int:backup_id>/download/", TenantBackupDownloadView.as_view()),
    path('webhooks/mercadopago/', MercadoPagoWebhookView.as_view())

] + router.urls
