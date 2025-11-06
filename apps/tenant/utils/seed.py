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
                "user": user,
                "opening_date": timezone.now(),
                "opening_balance": Decimal("0.00"),
                "closing_balance": Decimal("0.00"),
                "status": "open",
            }
        )

        concepts = [

            ("001", "Servicio de agua"),
            ("002", "Servicio de desagüe"),
            ("003", "Cargo fijo"),
            ("004", "Reconexión de servicio de agua"),
            ("005", "Corte de servicio de agua"),
            ("006", "Nueva instalación de servicio de agua"),
            ("007", "Pago por informe de factibilidad de servicio"),
            ("008", "Instalación de servicio de agua"),
            ("009", "Suscripción en el padrón de usuarios"),
            ("010", "Nueva instalación de servicio de desagüe"),
            ("011", "Pago por inspección ocular técnica"),
            ("012", "Pago por instalación de servicio de desagüe"),

        ]

        for code, name in concepts:

            CashConcept.objects.get_or_create(
                code=code,
                defaults={"name": name, "type": "income"}
            )