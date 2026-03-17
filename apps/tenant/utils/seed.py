from django_tenants.utils import schema_context
from apps.agua.models import CashBox, CashConcept, Company
from django.utils import timezone
from decimal import Decimal

def load_initial_data(schema_name, user, company_data):

    with schema_context(schema_name, user):

        Company.objects.create(**company_data)

        CashBox.objects.get_or_create(
            pk=1,
            defaults={
                "user_id": user.pk,
                "opening_date": timezone.now(),
                "opening_balance": Decimal("0.00"),
                "closing_balance": Decimal("0.00"),
                "status": "open",
            }
        )

        concepts = [
            ("001", "Servicio de agua", True, True, "price_water"),
            ("002", "Servicio de desagüe", True, True, "price_sewer"),
            ("003", "Cargo fijo", True, True, "price_fixed_charge"),
            ("004", "Limpieza publica", True, True, "price_clean"),
            ("005", "Igv", True, False, "price_igv"),
        ]

        for code, name, is_master, is_master_view, system_key in concepts:

            CashConcept.objects.get_or_create(
                code=code,
                defaults={"name": name, "type": "income", "is_master" : is_master, "is_master_view" : is_master_view, "system_key" : system_key }
            )