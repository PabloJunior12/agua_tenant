from rest_framework import routers
from django.urls import path
from .views import (
    CustomerViewSet, WaterMeterViewSet, CategoryViewSet, CashOutflowViewSet, ViaViewSet, CalleViewSet, CashBoxViewSet, CompanyViewSet,
    ReadingViewSet, InvoiceViewSet, ConfigViewSet, CrearCargoCulqiView, ZonaViewSet, DebtViewSet, NotificacionViewSet, ReadingGenerationViewSet, CashConceptViewSet, DailyCashReportViewSet, MorosidadOnTimeView, MorosidadOverdueView 
)
router = routers.DefaultRouter()

router.register("cash-out-flow", CashOutflowViewSet)
router.register("company", CompanyViewSet)
router.register("notify", NotificacionViewSet)
router.register("cash-concept", CashConceptViewSet)
router.register("categories", CategoryViewSet)
router.register("config", ConfigViewSet)
router.register("cash-box", CashBoxViewSet)
router.register('reading-generation', ReadingGenerationViewSet)
router.register('debts', DebtViewSet)
router.register('zonas', ZonaViewSet)
router.register('vias', ViaViewSet)
router.register('calles', CalleViewSet)
router.register('customers', CustomerViewSet)
router.register('meters', WaterMeterViewSet)
router.register('readings', ReadingViewSet)
router.register('invoices', InvoiceViewSet)
router.register('daily-cash-report', DailyCashReportViewSet)

urlpatterns = [

    path("morosidad/moroso/", MorosidadOverdueView.as_view()),
    path("morosidad/on-time/", MorosidadOnTimeView.as_view()),
    path('crear-cargo/', CrearCargoCulqiView.as_view(), name='crear-cargo'),


] + router.urls