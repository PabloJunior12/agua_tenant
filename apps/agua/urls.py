from rest_framework import routers
from django.urls import path
from .views import (
    CustomerViewSet, WaterMeterViewSet, AtypicalConsumptionReportExcelView, ServiceChargeViewSet, DebtRefinancingViewSet, ManzanaViewSet,CutBatchViewSet, CategoryViewSet, CashOutflowViewSet, ViaViewSet, CalleViewSet, CashBoxViewSet, CompanyViewSet,
    ReadingViewSet, InvoiceViewSet, MorosidadViewSet, DebtByConceptReportAPIView, MeterAssignmentViewSet, ServiceCutViewSet, ConfigViewSet, DashboardSummaryAPIView, ZonaViewSet, DebtViewSet, RefinancingInstallmentViewSet, ReadingGenerationViewSet, CashConceptViewSet, DailyCashReportViewSet, ProcessPayment, ProcessPaymentYape, PaymentStatusView
)

router = routers.DefaultRouter()

router.register("cash-out-flow", CashOutflowViewSet)
router.register("company", CompanyViewSet)
router.register("cash-concept", CashConceptViewSet)
router.register("categories", CategoryViewSet)
router.register("config", ConfigViewSet)
router.register("cash-box", CashBoxViewSet)
router.register('reading-generation', ReadingGenerationViewSet)
router.register('debts', DebtViewSet)
router.register('zonas', ZonaViewSet)
router.register('manzana', ManzanaViewSet)
router.register('vias', ViaViewSet)
router.register('calles', CalleViewSet)
router.register('customers', CustomerViewSet, basename="customers")
router.register('meters', WaterMeterViewSet)
router.register('meters-assignment', MeterAssignmentViewSet, basename="metersassignment")
router.register('readings', ReadingViewSet)
router.register('invoices', InvoiceViewSet)
router.register('daily-cash-report', DailyCashReportViewSet)
router.register('installments', RefinancingInstallmentViewSet)
router.register('service-cut', ServiceCutViewSet)
router.register('cut-batch', CutBatchViewSet)
router.register('morosidad', MorosidadViewSet, basename="morosidad")
router.register('debt-refinancing', DebtRefinancingViewSet, basename="debtrefinancing")
router.register('service-charge', ServiceChargeViewSet)

urlpatterns = [

    path("summary/", DashboardSummaryAPIView.as_view()),
    path("crear-pago/", ProcessPayment.as_view()),
    path("pagar-yape/", ProcessPaymentYape.as_view()),
    path("payment-status/<str:payment_id>/", PaymentStatusView.as_view()),
    path("reports/atypical-consumption/excel/", AtypicalConsumptionReportExcelView.as_view()),
    path("reports/debts-by-concept/", DebtByConceptReportAPIView.as_view()),


] + router.urls