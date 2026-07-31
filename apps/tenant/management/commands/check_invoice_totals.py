# apps/agua/management/commands/check_invoice_consistency.py

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Sum
from django.db.models.functions import Coalesce

from django_tenants.utils import get_tenant_model, tenant_context

from apps.agua.models import (
    Invoice,
    InvoiceDebt,
    InvoiceConcept,
    InvoiceInstallment,
    InvoicePayment,
)


class Command(BaseCommand):
    help = "Verifica inconsistencias entre facturas, detalles y pagos."

    def handle(self, *args, **options):

        TenantModel = get_tenant_model()

        total_inconsistencias = 0

        for tenant in TenantModel.objects.exclude(schema_name="public"):

            self.stdout.write("")
            self.stdout.write("=" * 80)
            self.stdout.write(f"TENANT: {tenant.schema_name}")
            self.stdout.write("=" * 80)

            inconsistencias = 0

            with tenant_context(tenant):

                invoices = Invoice.objects.all().order_by("id")

                for invoice in invoices:

                    total_invoice = invoice.total or Decimal("0.00")

                    total_debts = InvoiceDebt.objects.filter(
                        invoice=invoice
                    ).aggregate(
                        total=Coalesce(Sum("total"), Decimal("0.00"))
                    )["total"]

                    total_concepts = InvoiceConcept.objects.filter(
                        invoice=invoice
                    ).aggregate(
                        total=Coalesce(Sum("total"), Decimal("0.00"))
                    )["total"]

                    total_installments = InvoiceInstallment.objects.filter(
                        invoice=invoice
                    ).aggregate(
                        total=Coalesce(Sum("total"), Decimal("0.00"))
                    )["total"]

                    total_details = (
                        total_debts +
                        total_concepts +
                        total_installments
                    )

                    total_payments = InvoicePayment.objects.filter(
                        invoice=invoice
                    ).aggregate(
                        total=Coalesce(Sum("total"), Decimal("0.00"))
                    )["total"]

                    problems = []

                    if total_invoice != total_details:
                        problems.append(
                            f"DETALLE ({total_details}) DIF={total_invoice-total_details}"
                        )

                    if total_invoice != total_payments:
                        problems.append(
                            f"PAGOS ({total_payments}) DIF={total_invoice-total_payments}"
                        )

                    if problems:

                        inconsistencias += 1
                        total_inconsistencias += 1

                        self.stdout.write(
                            self.style.ERROR(
                                f"""
Factura : {invoice.code}
Cliente : {invoice.customer}
Total   : {total_invoice}
Deudas  : {total_debts}
Concept.: {total_concepts}
Cuotas  : {total_installments}
Detalle : {total_details}
Pagos   : {total_payments}
Problema: {' | '.join(problems)}
------------------------------------------------------------
""".rstrip()
                            )
                        )

            if inconsistencias == 0:
                self.stdout.write(
                    self.style.SUCCESS("✓ Sin inconsistencias.")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Se encontraron {inconsistencias} inconsistencias."
                    )
                )

        self.stdout.write("")
        self.stdout.write("=" * 80)
        self.stdout.write(
            self.style.SUCCESS(
                f"TOTAL DE INCONSISTENCIAS: {total_inconsistencias}"
            )
        )
        self.stdout.write("=" * 80)