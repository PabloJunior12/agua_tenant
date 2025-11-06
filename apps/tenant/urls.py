# apps/tenants/public_urls.py

from django.urls import path
from apps.tenant.views import  ClientViewSet, ValidateTenantView
from rest_framework import routers


router = routers.DefaultRouter()

router.register("client", ClientViewSet)

urlpatterns = [

    path('tenants/validate/<str:schema_name>/', ValidateTenantView.as_view()),

] + router.urls
