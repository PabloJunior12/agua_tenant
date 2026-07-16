from decimal import Decimal
from django.db import models
from django.db.models import (
    Sum, OuterRef, Subquery, DecimalField,
    Value, F, ExpressionWrapper
)
from django.db.models.functions import Coalesce

from django.apps import apps
DECIMAL_FIELD = DecimalField(max_digits=10, decimal_places=2)

class CustomerQuerySet(models.QuerySet):

    def with_total_debt(self):

        Debt = apps.get_model("agua", "Debt")
        ServiceCharge = apps.get_model("agua", "ServiceCharge")
        RefinancingInstallment = apps.get_model("agua", "RefinancingInstallment")

        debt_total = Debt.objects.filter(
            customer=OuterRef("pk"),
            paid=False,
            is_refinanced=False,
        ).values("customer").annotate(
            total=Sum("amount")
        ).values("total")

        service_total = ServiceCharge.objects.filter(
            customer=OuterRef("pk"),
            status="pending",
            is_refinanced=False,
        ).values("customer").annotate(
            total=Sum("amount")
        ).values("total")

        refinancing_total_subquery = RefinancingInstallment.objects.filter(
            refinancing__customer=OuterRef("pk"),
            paid=False,
        ).values(
            "refinancing__customer"
        ).annotate(
            total=Sum("total_amount")
        ).values("total")

        return self.annotate(

            debt_total=Coalesce(
                Subquery(debt_total, output_field=DECIMAL_FIELD),
                Value(Decimal("0.00"), output_field=DECIMAL_FIELD),
            ),

            service_total=Coalesce(
                Subquery(service_total, output_field=DECIMAL_FIELD),
                Value(Decimal("0.00"), output_field=DECIMAL_FIELD),
            ),

            refinancing_total=Coalesce(
                Subquery(refinancing_total_subquery, output_field=DECIMAL_FIELD),
                Value(Decimal("0.00"), output_field=DECIMAL_FIELD),
            ),

        ).annotate(

            total_debt=ExpressionWrapper(
                F("debt_total") +
                F("service_total") +
                F("refinancing_total"),
                output_field=DECIMAL_FIELD,
            )

        )