from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.agua.models import InvoiceDebt


class Command(BaseCommand):
    help = "Audita deudas pagadas en el tenant chilca"

    def handle(self, *args, **options):

        with schema_context("pangoa"):

            invoice_debts = (
                InvoiceDebt.objects
                .select_related(
                    "invoice",
                    "debt",
                    "debt__customer",
                )
                .filter(
                    invoice__status="active",
                    debt__paid=False,
                )
                .order_by("invoice__code")
            )

            self.stdout.write(
                self.style.WARNING(
                    f"Se encontraron {invoice_debts.count()} inconsistencias."
                )
            )

            for item in invoice_debts:
                self.stdout.write(
                    f"Factura: {item.invoice.code} | "
                    f"Cliente: {item.debt.customer.full_name} | "
                    f"Periodo: {item.debt.period} | "
                    f"Deuda pagada: {item.debt.paid}"
                )