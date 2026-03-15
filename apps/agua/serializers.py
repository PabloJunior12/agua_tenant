from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist
from django.utils.timezone import now
from django.conf import settings
from .models import Customer, WaterMeter, CashBox, Company, Config, CashOutflow, InvoiceConcept, CashMovement, DebtDetail, CashConcept, Reading, ReadingGeneration, Invoice, Category, Via, Calle, InvoiceDebt, Zona, Debt, InvoicePayment, DailyCashReport
from .utils import next_month_date, get_reading_status
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from rest_framework.exceptions import ValidationError
from django.contrib.auth import get_user_model

import os

User = get_user_model()

class ZonaSerializer(serializers.ModelSerializer):

    class Meta:

        model = Zona
        fields = '__all__'

class CalleSerializer(serializers.ModelSerializer):

    via_name = serializers.CharField(source='via.name', read_only=True)

    class Meta:

        model = Calle
        fields = ['id', 'via', 'via_name', 'name','codigo','zona']

class WaterMeterSerializer(serializers.ModelSerializer):

    customer = serializers.PrimaryKeyRelatedField(queryset=Customer.objects.all())

    class Meta:
        model = WaterMeter
        fields = ['id', 'code', 'installation_date', 'customer']

    def validate_customer(self, value):
        if WaterMeter.objects.filter(customer=value).exists():
            raise serializers.ValidationError("Este cliente ya tiene un medidor asignado.")
        return value

class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        
        model = Category
        fields = '__all__'

class DebtDetailSerializer(serializers.ModelSerializer):

    class Meta:
        model = DebtDetail
        fields = "__all__"

    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Agregar toda la data del cliente usando CustomerSerializer
        data['concept'] = CashConceptSerializer(instance.concept).data
        return data

class DebtSerializer(serializers.ModelSerializer):

    details = DebtDetailSerializer(many=True, read_only=True)

    class Meta:
        model = Debt
        fields = '__all__'

class CustomerSerializer(serializers.ModelSerializer):

    total_debt = serializers.SerializerMethodField()

    class Meta:

        model = Customer
        fields = '__all__'

    def to_representation(self, instance):

        data = super().to_representation(instance)

        data['category'] = CategorySerializer(instance.category).data

        if instance.has_meter and hasattr(instance, 'meter'):
            data['meter'] = {
                'code': instance.meter.code,
                'installation_date': instance.meter.installation_date
            }
        else:
            data['meter'] = None

        # calle como objeto
        if instance.calle:
            data['calle'] = CalleSerializer(instance.calle).data
        else:
            data['calle'] = None

        # calle como objeto
        if instance.zona:
            data['zona'] = ZonaSerializer(instance.zona).data
        else:
            data['zona'] = None

        return data

    def get_total_debt(self, obj):
        # Sumamos las deudas pendientes
        return obj.debts.filter(paid=False).aggregate(total=Sum("amount"))["total"] or 0

class CustomerWithDebtsSerializer(serializers.ModelSerializer):

    calle = CalleSerializer()
    zona = ZonaSerializer()
    debts = serializers.SerializerMethodField()
    total_debt = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = '__all__'

    def get_debts(self, obj):
        # solo traemos las deudas pendientes
        debts = obj.debts.filter(paid=False).order_by("-period")
        return DebtSerializer(debts, many=True).data
    
    def get_total_debt(self, obj):
        # Sumamos las deudas pendientes
        return obj.debts.filter(paid=False).aggregate(total=Sum("amount"))["total"] or 0

class CashBoxSerializer(serializers.ModelSerializer):

    user = serializers.SerializerMethodField(read_only=True)

    class Meta:

        model = CashBox
        fields = '__all__'

    def get_user(self, obj):
        try:
            user = User.objects.get(id=obj.user_id)
            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            }
        except User.DoesNotExist:
            return None

class DailyCashReportSerializer(serializers.ModelSerializer):

    class Meta:

        model = DailyCashReport
        fields = '__all__'

class CashConceptSerializer(serializers.ModelSerializer):

    system_key_name = serializers.CharField(
        source='get_system_key_display',
        read_only=True
    )

    class Meta:
        model = CashConcept
        fields = "__all__"

class MorosidadSerializer(serializers.ModelSerializer):
    
    last_reading_status = serializers.SerializerMethodField()
    last_due_date = serializers.SerializerMethodField()
    total_debt = serializers.SerializerMethodField()
    unpaid_months = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "id",
            "full_name",
            "codigo",
            "address",
            "number",
            "last_reading_status",
            "last_due_date",
            "total_debt",
            "unpaid_months",
        ]

    def get_last_reading_status(self, obj):
    
        d = obj.debts.filter(paid=False).order_by('-period').first()
        return "overdue" if d else None

    def get_last_due_date(self, obj):
        d = obj.debts.filter(paid=False).order_by('-period').first()
        return d.reading.date_of_due if (d and d.reading) else None

    def get_total_debt(self, obj):
        return obj.debts.filter(paid=False).aggregate(
            total=Sum('amount')
        )['total'] or 0

    def get_unpaid_months(self, obj):
        return obj.debts.filter(paid=False).count()

class ReadingSerializer(serializers.ModelSerializer):

    class Meta:
        model = Reading
        fields = '__all__'
    
    def validate(self, data):
        
        customer = data.get('customer', self.instance.customer if self.instance else None)
        period = data.get('period', self.instance.period if self.instance else None)
        current_reading = data.get('current_reading', self.instance.current_reading if self.instance else None)

        if not customer or not period:

            return data

        # ✅ Solo aplicar validaciones si el cliente tiene medidor
        if not customer.has_meter:
            
            return data

        # 1) Evitar lecturas duplicadas en el mismo mes y cliente
        qs = Reading.objects.filter(
            customer=customer,
            period__year=period.year,
            period__month=period.month
        )

        if self.instance:

            qs = qs.exclude(id=self.instance.id)

        if qs.exists():

            raise ValidationError(
                "Ya existe una lectura registrada para este cliente en el mismo mes."
            )

        # Buscar lectura anterior y siguiente
        prev_reading = Reading.objects.filter(
            customer=customer, period__lt=period
        ).order_by("-period").first()

        next_reading = Reading.objects.filter(
            customer=customer, period__gt=period
        ).order_by("period").first()

        # --- VALIDACIÓN LECTURA MENOR ---
        if prev_reading:
            # Caso normal: hay historial real
            if current_reading < prev_reading.current_reading:
                raise ValidationError(f"La lectura no puede ser menor que la de {prev_reading.period} ({prev_reading.current_reading}).")
        else:
            # Caso MIGRACIÓN: no hay historial, se compara contra previous_reading manual
            manual_previous = data.get('previous_reading', Decimal('0.000'))

            if current_reading < manual_previous:
                raise ValidationError("La lectura actual no puede ser menor que la lectura anterior ingresada manualmente.")

        # --- VALIDACIÓN LECTURA MAYOR ---
        if next_reading:

            if current_reading > next_reading.current_reading:

                raise ValidationError(f"La lectura no puede ser mayor que la de {next_reading.period} ({next_reading.current_reading}).")
            
        # 2) Evitar registrar un mes anterior si ya existe uno posterior
        future_qs = Reading.objects.filter(
            customer=customer,
            period__gt=period,
            paid=True
        )
        if future_qs.exists():
            raise ValidationError(
                "No se puede editar porque existen lecturas posteriores ya pagadas."
            )

        # 3) Verificar que no se salten meses.
        #    Obtenemos la última lectura (mes anterior) y comprobamos que la nueva sea el mes siguiente.
        last_reading = Reading.objects.filter(
            customer=customer,
            period__lt=period
        ).order_by('-period').first()

        if last_reading:
            # Calculamos la fecha del "próximo mes" a partir de la última lectura
            expected_next_date = next_month_date(last_reading.period)

            # Comparamos solo año y mes (en caso de que no uses día=1):
            if (period.year != expected_next_date.year) or (period.month != expected_next_date.month):
                raise ValidationError(
                    "Debes registrar el mes consecutivo. El siguiente mes esperado es: "
                    f"{expected_next_date.strftime('%B %Y')}"
                )

            # (Opcional) Verificar que current_reading >= last_reading.current_reading
            if current_reading < last_reading.current_reading:
                raise ValidationError(
                    "La lectura actual no puede ser menor que la última lectura registrada."
                )
        else:
            # Si no hay lecturas previas, esta es la primera: no hay mes anterior que validar.
            pass

        return data

class ReadingGenerationSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ReadingGeneration
        # fields = ["id", "period", "created_at", "created_by_name", "total_generated", "notes"]
        fields = '__all__'

    def get_created_by_name(self, obj):
        return obj.created_by.get_username() if obj.created_by else "Sistema"

class InvoiceDebtSerializer(serializers.ModelSerializer):

    class Meta:

        model = InvoiceDebt
        fields = ['debt']

class InvoiceConceptSerializer(serializers.ModelSerializer):
    concept = serializers.PrimaryKeyRelatedField(queryset=CashConcept.objects.all())

    class Meta:
        model = InvoiceConcept
        exclude = ['invoice']  # 👈 no se envía desde Angular
        
class InvoicePaymentSerializer(serializers.ModelSerializer):

    class Meta:
        model = InvoicePayment
        exclude = ['invoice']
        read_only_fields = ['created_at']

class InvoiceSerializer(serializers.ModelSerializer):
    
    customer = serializers.PrimaryKeyRelatedField(
        queryset=Customer.objects.all(),
        required=False,
        allow_null=True
    )

    invoice_concepts = InvoiceConceptSerializer(many=True, required=False)
    invoice_debts = InvoiceDebtSerializer(many=True)
    invoice_payments = InvoicePaymentSerializer(many=True)

    class Meta:
        model = Invoice
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # Agregar toda la data del cliente usando CustomerSerializer
        data['customer'] = CustomerSerializer(instance.customer).data

        return data

    def create(self, validated_data):
        debts_data = validated_data.pop("invoice_debts", [])
        concepts_data = validated_data.pop("invoice_concepts", [])
        payments_data = validated_data.pop("invoice_payments", [])

        # 1. Si no se envió cliente (por ser pagador externo)
        if not validated_data.get("customer"):
            try:
                default_customer = Customer.objects.get(codigo="00000")  # o "000000"
            except Customer.DoesNotExist:
                raise serializers.ValidationError({
                    "error": "No existe el cliente genérico con código '00000'."
                })
            validated_data["customer"] = default_customer

        with transaction.atomic():
            invoice = Invoice.objects.create(**validated_data)
            total = 0

            # --- CASO 1: COBRO DE DEUDAS ---
            if debts_data:
                selected_debts = [item["debt"] for item in debts_data]
                selected_debts = sorted(selected_debts, key=lambda d: d.period)
                # customer = validated_data["customer"]
                # all_unpaid = Debt.objects.filter(customer=customer, paid=False).order_by("period")

                # if all_unpaid.exists():
                #     first_unpaid = all_unpaid.first().period
                #     if selected_debts[0].period != first_unpaid:
                #         raise serializers.ValidationError({
                #             "error": f"Debes pagar empezando desde {first_unpaid.strftime('%m-%Y')}."
                #         })

                # for i in range(1, len(selected_debts)):
                #     prev = selected_debts[i - 1].period
                #     curr = selected_debts[i].period
                #     diff = (curr.year - prev.year) * 12 + (curr.month - prev.month)
                #     if diff != 1:
                #         raise serializers.ValidationError({
                #             "error": "Las deudas deben pagarse en meses consecutivos."
                #         })

                for item in debts_data:
                    debt = item["debt"]
                    InvoiceDebt.objects.create(invoice=invoice, debt=debt, total=debt.amount)
                    debt.paid = True
                    debt.save()

                    if debt.reading:
                        debt.reading.paid = True
                        debt.reading.save(skip_process=True)

                    total += debt.amount

            # --- CASO 2: PAGO DE CONCEPTOS ---
            elif concepts_data:
                for item in concepts_data:
                    # ahora concept es un PrimaryKeyRelatedField (solo el id)
                    concept = item["concept"]
                    total_concept = item.get("total", 0)
                    description = item.get("description")

                    InvoiceConcept.objects.create(
                        invoice=invoice,
                        concept=concept,
                        description=description,
                        total=total_concept
                    )
                    total += total_concept

            else:
                raise serializers.ValidationError({
                    "error": "Debe incluir deudas o conceptos para registrar la factura."
                })

            # --- REGISTRAR PAGOS ---
            payments_total = 0
            for item in payments_data:
                payment = InvoicePayment.objects.create(
                    invoice=invoice,
                    method=item["method"],
                    total=item["total"],
                    reference=item.get("reference"),
                    cashbox=item["cashbox"]
                )

                if debts_data:
                    for inv_debt in invoice.invoice_debts.all():
                        for detail in inv_debt.debt.details.all():
                            CashMovement.objects.create(
                                cashbox=item["cashbox"],
                                concept=detail.concept,
                                method=item["method"],
                                total=detail.amount,
                                reference=item.get("reference"),
                                invoice_payment=payment
                            )

                elif concepts_data:
                    for inv_concept in invoice.invoice_concepts.all():
                        CashMovement.objects.create(
                            cashbox=item["cashbox"],
                            concept=inv_concept.concept,
                            method=item["method"],
                            total=inv_concept.total,
                            reference=item.get("reference"),
                            invoice_payment=payment
                        )

                payments_total += item["total"]

            if round(payments_total, 2) != round(total, 2):
                raise serializers.ValidationError({
                    "payments": f"Los pagos ({payments_total}) no cuadran con el total ({total})"
                })

            invoice.total = total
            invoice.save()

        return invoice

class InvoiceAutoSerializer(serializers.Serializer):
    
    customer_id = serializers.IntegerField()
    debt_ids = serializers.ListField(
        child=serializers.IntegerField(),
        allow_empty=False
    )
    payment_reference = serializers.CharField()
    method = serializers.CharField()

    def validate(self, data):
        """
        Validaciones mínimas y técnicas.
        No reglas humanas (eso ya lo decidió MP).
        """

        customer_id = data["customer_id"]
        debt_ids = data["debt_ids"]

        customer = Customer.objects.filter(id=customer_id).first()
        if not customer:
            raise serializers.ValidationError("Cliente no existe.")

        debts = Debt.objects.filter(
            id__in=debt_ids,
            customer=customer,
            paid=False
        ).order_by("period")

        if not debts.exists():
            raise serializers.ValidationError("No hay deudas válidas para pagar.")
        
        data["customer"] = customer
        data["debts"] = debts

        return data
    
    def create(self, validated_data):
        
        customer = validated_data["customer"]
        debts = validated_data["debts"]
        payment_reference = validated_data["payment_reference"]
        method = validated_data["method"]

        with transaction.atomic():

            cashbox = CashBox.objects.first() 

            #  Crear factura
            invoice = Invoice.objects.create(
                customer=customer,
                reference="debt",
                notes="Pago online Mercado Pago",
                payment_reference=payment_reference,
                payment_origin="gateway",
            )

            total = 0

            # Relacionar deudas
            for debt in debts:
                InvoiceDebt.objects.create(
                    invoice=invoice,
                    debt=debt,
                    total=debt.amount
                )

                debt.paid = True
                debt.save()

                if debt.reading:
                    debt.reading.paid = True
                    debt.reading.save(skip_process=True)

                total += debt.amount

            # Registrar pago (ONLINE → sin caja)
            payment = InvoicePayment.objects.create(
                invoice=invoice,
                method=method,
                total=total,
                reference=payment_reference,
                cashbox=cashbox
            )

            # 4️⃣ Movimientos contables
            for debt in debts:
                for detail in debt.details.all():
                    CashMovement.objects.create(
                        cashbox=cashbox,
                        concept=detail.concept,
                        method=method,
                        total=detail.amount,
                        reference=payment_reference,
                        invoice_payment=payment
                    )

            # 5️⃣ Total factura
            invoice.total = total
            invoice.save()

        return invoice

class ViaSerializer(serializers.ModelSerializer):


    class Meta:
        
        model = Via
        fields = '__all__'

class CompanySerializer(serializers.ModelSerializer):

    class Meta:
        model = Company
        fields = '__all__'

    def update(self, instance, validated_data):
        # Verificar si hay un nuevo logo
        new_logo = validated_data.get("logo", None)
        if new_logo and instance.logo:
            # Eliminar el logo anterior del sistema de archivos
            old_logo_path = os.path.join(settings.MEDIA_ROOT, str(instance.logo))
            if os.path.exists(old_logo_path):
                os.remove(old_logo_path)

        instance.logo = new_logo if new_logo else instance.logo  # Mantener el anterior si no se envía nuevo
        instance.name = validated_data.get("name", instance.name)
        instance.ruc = validated_data.get("ruc", instance.ruc)
        instance.address = validated_data.get("address", instance.address)

        instance.save()
        return instance

class CashOutflowSerializer(serializers.ModelSerializer):

    class Meta:
        model = CashOutflow
        fields = "__all__"

class ConfigSerializer(serializers.ModelSerializer):

    class Meta:
        
        model = Config
        fields = '__all__'

# class PaymentMethodSerializer(serializers.ModelSerializer):

#     class Meta:

#         model = PaymentMethod
#         fields = '__all__'

# class YearSerializer(serializers.ModelSerializer):

#     class Meta:
        
#         model = Year
#         fields = '__all__'
