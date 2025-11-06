from django.db import models
from apps.base.models import BaseModel
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import timedelta, date
from dateutil.relativedelta import relativedelta
from django.utils.timezone import now
from django.conf import settings


class Company(models.Model):

    name = models.CharField(max_length=255, verbose_name="Nombre de la empresa")
    ruc = models.CharField(max_length=11, unique=True, verbose_name="RUC")
    address = models.CharField(max_length=255, verbose_name="Dirección", null=True, blank=True)
    phone = models.CharField(max_length=20, verbose_name="Teléfono", null=True, blank=True)
    email = models.EmailField(verbose_name="Correo electrónico", null=True, blank=True)
    logo = models.ImageField(upload_to="logos/", verbose_name="Logo", null=True, blank=True)

    def __str__(self):
        return self.name

class Zona(models.Model):

    codigo = models.CharField(max_length=4)
    name = models.CharField(max_length=100, verbose_name="Nombre de la Zona")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"

class Via(models.Model):

    codigo = models.CharField(max_length=2, unique=True, editable=False)
    name = models.CharField(max_length=50)

    def save(self, *args, **kwargs):

        # Solo generar el código si no existe

        if not self.codigo:

            last_via = Via.objects.order_by('-id').first()

            next_number = 1 if not last_via else int(last_via.codigo) + 1

            self.codigo = str(next_number).zfill(2)  # genera "01", "02", "03"...

        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Calle(models.Model):

    codigo = models.CharField(max_length=4, unique=True, editable=False)
    via = models.ForeignKey(Via, on_delete=models.CASCADE, related_name='calles')
    name = models.CharField(max_length=100)

    def save(self, *args, **kwargs):
        # Generar código automáticamente si no existe
        if not self.codigo:
            last_calle = Calle.objects.exclude(codigo__isnull=True).exclude(codigo='').order_by('-id').first()
            try:
                next_number = int(last_calle.codigo) + 1 if last_calle else 1
            except ValueError:
                next_number = 1
            self.codigo = str(next_number).zfill(4)  # genera "0001", "0002", ...
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

class Category(models.Model):
    
    codigo = models.CharField(max_length=2, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    min_consumption = models.IntegerField(null=True, blank=True)  # Desde qué m³ aplica
    max_consumption = models.IntegerField(null=True, blank=True)

    extra_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    price_water = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de agua")
    price_sewer = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de alcantarillado")

    has_meter = models.BooleanField(default=True)
    state = models.BooleanField(default=True) 

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Categoría"
        verbose_name_plural = "Categorías"

    def save(self, *args, **kwargs):

        if not self.codigo:
            last_invoice = Category.objects.order_by('-id').first()
            next_number = 1 if not last_invoice else int(last_invoice.codigo) + 1
            self.codigo = str(next_number).zfill(2)  # "0000001"
        super().save(*args, **kwargs)

class CashBox(models.Model):

    STATUS_CHOICES = [
        ("open", "Abierta"),
        ("closed", "Cerrada"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cashboxes")
    opening_date = models.DateTimeField(auto_now_add=True)
    closing_date = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")

    def __str__(self):

        return f"Caja {self.id} - {self.user.username}"

class DailyCashReport(models.Model):

    cashbox = models.ForeignKey(CashBox, on_delete=models.CASCADE, related_name="daily_reports")
    date = models.DateField()
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  # saldo de ayer
    total_incomes = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_outcomes = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    confirmed = models.BooleanField(default=False)  # ✅ si el usuario ya conformó

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        unique_together = ("cashbox", "date")  # solo 1 reporte por caja y día

class CashConcept(models.Model):

    code = models.CharField(max_length=3, unique=True, null=True, blank=True)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=15)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        # Solo generar el código si no existe
        if not self.code:
            last_concept = CashConcept.objects.order_by('-id').first()
            next_number = 1 if not last_concept else int(last_concept.code) + 1
            self.code = str(next_number).zfill(3)  # genera "001", "002", "003", ...
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    def __str__(self):
        return f"{self.code} - {self.name} ({self.get_type_display()})"
  
class Customer(models.Model):

    ESTADO_CHOICES = [
        ("active", "Activo"),
        ("inactive", "Inactivo"),
        ("suspended", "Suspendido"),
    ]


    codigo = models.CharField(max_length=5, null=True, blank=True)
    identity_document_type = models.IntegerField(default=1)
    full_name = models.CharField(max_length=200)
    number = models.CharField(max_length=15, blank=True, null=True)  # Ya no unique
    address = models.CharField(max_length=255, null=True, blank=True)
    has_meter = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="customers")
    calle = models.ForeignKey(Calle, on_delete=models.PROTECT, null=True)
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT, null=True)
    mz = models.CharField(max_length=15, blank=True, null=True)
    lote = models.CharField(max_length=15, blank=True, null=True)
    nro = models.CharField(max_length=15, blank=True, null=True)

    # 🔹 Nuevo campo
    state = models.CharField(
        max_length=15,
        choices=ESTADO_CHOICES,
        default="active",
    )

    def __str__(self):
        return f"{self.full_name} ({self.number or 'sin DNI'})"

class WaterMeter(models.Model):
    
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name="meter")
    code = models.CharField(max_length=50, unique=True)  # único globalmente
    installation_date = models.DateField()

    def __str__(self):
        return f"{self.code} - {self.customer.full_name}"

class Reading(models.Model):
    
    customer = models.ForeignKey('Customer', related_name='readings', on_delete=models.CASCADE)
    period = models.DateField()  # Ej. 2025-07-01

    date_of_issue = models.DateField(null=True)
    date_of_due = models.DateField(null=True)
    date_of_cute = models.DateField(null=True)

    current_reading = models.DecimalField(max_digits=10, decimal_places=3)
    previous_reading = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)
    consumption = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)

    total_water = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_sewer = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_fixed_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    paid = models.BooleanField(default=False)
    has_meter = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        unique_together = ('customer', 'period')
        ordering = ['-period']

    def __str__(self):

        return f"{self.customer.full_name} - {self.period.strftime('%Y-%m')}"

    # -------------------------------
    # Cálculos de consumo y tarifas
    # -------------------------------
    def calculate_consumption(self):

        tariff = self.customer.category

        self.has_meter = self.customer.has_meter

        if tariff.has_meter:
            # Buscar lectura anterior
            previous = Reading.objects.filter(
                customer=self.customer,
                period__lt=self.period
            ).order_by('-period').first()

            if previous:
                self.previous_reading = previous.current_reading
                self.consumption = self.current_reading - previous.current_reading
            else:
                self.previous_reading = Decimal('0.000')
                self.consumption = self.current_reading
        else:
            # Sin medidor: todo fijo
            self.previous_reading = Decimal('0.000')
            self.consumption = Decimal('0.000')

    def calculate_industrial_tariff(self, tariff):

        """Calcula tarifa INDUSTRIAL con exceso"""
        consumo_base = min(self.consumption, tariff.max_consumption)
        exceso = max(0, self.consumption - tariff.max_consumption)
        return (consumo_base * tariff.price_water) + (exceso * tariff.extra_rate)

    def calculate_total(self):

        cargo_fijo = CashConcept.objects.get(code="003")
              
        total_fixed_charge = cargo_fijo.total if cargo_fijo else Decimal("0.00")

        tariff = self.customer.category

        if tariff.has_meter:

            if tariff.max_consumption:

                self.total_water = self.calculate_industrial_tariff(tariff)

            else:

                self.total_water = self.consumption * tariff.price_water
        else:
            self.total_water = tariff.price_water
            self.previous_reading = Decimal('0.000')
            self.consumption = Decimal('0.000')

        self.total_sewer = tariff.price_sewer
        self.total_fixed_charge = total_fixed_charge
        self.total_amount = self.total_water + self.total_sewer + self.total_fixed_charge

        return self.total_amount

    # -------------------------------
    # Sincronización con deudas
    # -------------------------------
    def _sync_debt(self):

        from .models import Debt, DebtDetail, CashConcept

        normalized_period = date(self.period.year, self.period.month, 1)

        debt, created = Debt.objects.get_or_create(
            customer=self.customer,
            period=normalized_period,
            defaults={
                "reading": self,
                "amount": self.total_amount,
                "description": "Deuda por consumo de agua/desagüe",
            }
        )

        if not created:

            if debt.paid:

                # 🔒 Si la deuda ya está pagada, no se puede modificar
                raise ValidationError(
                    f"No se puede modificar la lectura de {self.period.strftime('%Y-%m')} porque ya está pagada."
                )
            
            debt.reading = self
            debt.amount = self.total_amount
            debt.save()

        # recreamos detalles
        debt.details.all().delete()

        if self.total_water > 0:
            DebtDetail.objects.create(
                debt=debt,
                concept=CashConcept.objects.get(code="001"),
                amount=self.total_water
            )

        if self.total_sewer > 0:
            DebtDetail.objects.create(
                debt=debt,
                concept=CashConcept.objects.get(code="002"),
                amount=self.total_sewer
            )

        if self.total_fixed_charge > 0:
            DebtDetail.objects.create(
                debt=debt,
                concept=CashConcept.objects.get(code="003"),
                amount=self.total_fixed_charge
            )

    # -------------------------------
    # Guardado con cascada
    # -------------------------------
    def save(self, *args, skip_process=False, **kwargs):

        if not skip_process:
            # Calcular consumo + total de esta lectura
            self.calculate_consumption()
            self.calculate_total()

            # Guardar lectura actual
            super().save(*args, **kwargs)

            # Crear o actualizar deuda
            self._sync_debt()

            # 🔄 Recalcular en cascada los meses posteriores
            next_readings = Reading.objects.filter(
                customer=self.customer,
                period__gt=self.period
            ).order_by('period')

            previous = self
            for r in next_readings:
                # Si ya está pagada, no continuar con la cadena
                if r.paid:
                    break

                r.previous_reading = previous.current_reading
                r.calculate_consumption()
                r.calculate_total()
                super(Reading, r).save(update_fields=[
                    "previous_reading", "consumption",
                    "total_water", "total_sewer",
                    "total_fixed_charge", "total_amount"
                ])
                r._sync_debt()
                previous = r

        else:

            # ⚡ Guardar directo sin procesos
            super().save(*args, **kwargs)

class Debt(models.Model):
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="debts")
    period = models.DateField()  # Ej. 2025-02-01
    description = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # suma de detalles
    paid = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reading = models.OneToOneField("Reading", on_delete=models.SET_NULL, null=True, blank=True, related_name="debt")

    class Meta:
        ordering = ['-period']

    def __str__(self):
        return f"{self.customer.full_name} - {self.period.strftime('%Y-%m')} - {self.amount}"
    
    def delete(self, *args, **kwargs):
        # Guardar el ID de la lectura antes de eliminar la deuda
        reading_id = self.reading_id

        # Eliminar la deuda
        super().delete(*args, **kwargs)

        # Si había una lectura asociada, intentar eliminarla
        if reading_id:
            try:
                reading = Reading.objects.get(id=reading_id)
                # Solo eliminar si sigue sin deuda asociada (verificación segura)
                if not getattr(reading, "debt", None):
                    reading.delete()
            except Reading.DoesNotExist:
                pass

    def __str__(self):

        return f"{self.customer.full_name} - {self.period.strftime('%Y-%m')} - {self.amount}"

class DebtDetail(models.Model):

    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="details")
    concept = models.ForeignKey(CashConcept, on_delete=models.PROTECT)  # Agua, Desagüe, Cargo fijo, Mora
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.debt.customer.full_name} - {self.concept.name}: {self.amount}"

class Invoice(models.Model):

    STATUS_CHOICES = [
        ('active', 'Activa'),
        ('cancelled', 'Anulada'),
    ]

    name_optional = models.CharField(max_length=200, blank=True, null=True)
    number_optional = models.CharField(max_length=15, blank=True, null=True)
    code = models.CharField(max_length=7, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    date = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reference = models.CharField(max_length=100, blank=True, null=True)  # N° operación bancaria, etc.
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')  # 👈
    created_at = models.DateTimeField(auto_now_add=True)

    def cancel(self):
        """Anula la factura y libera las deudas asociadas"""

        if self.status == "cancelled":
            return  # ya estaba anulada

        # liberar deudas
        for inv_debt in self.invoice_debts.all():
            debt = inv_debt.debt
            debt.paid = False
            debt.save()

            if debt.reading:
                debt.reading.paid = False
                debt.reading.save(skip_process=True)

        # solo marcar factura como anulada
        self.status = "cancelled"
        self.save()

    def save(self, *args, **kwargs):
        if not self.code:
            last_invoice = Invoice.objects.order_by('-id').first()
            next_number = 1 if not last_invoice else int(last_invoice.code) + 1
            self.code = str(next_number).zfill(7)
        super().save(*args, **kwargs)

    def __str__(self):

        return f"Factura {self.id} - {self.customer.full_name}"

class InvoiceDebt(models.Model):

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_debts')
    debt = models.ForeignKey(Debt, on_delete=models.CASCADE, related_name="invoice_links")
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('invoice', 'debt')

class InvoicePayment(models.Model):

    PAYMENT_METHODS = [
        ("cash", "Efectivo"),
        ("yape", "Yape"),
        ("plin", "Plin"),
        ("card", "Tarjeta"),
    ]

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="invoice_payments"
    )
    cashbox = models.ForeignKey(
        CashBox,
        on_delete=models.PROTECT,
        related_name="payments",
        null=True,
        blank=True
    )
    method = models.CharField(max_length=10, choices=PAYMENT_METHODS)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True)  # N° operación (Yape/Plin)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Pago de factura"
        verbose_name_plural = "Pagos de factura"

    def __str__(self):
        return f"{self.invoice.code} - {self.get_method_display()} {self.total}"

class InvoiceConcept(models.Model):

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_concepts')
    concept = models.ForeignKey(CashConcept, on_delete=models.PROTECT)
    description = models.CharField(max_length=255, blank=True, null=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)

class CashMovement(models.Model):
    
    cashbox = models.ForeignKey(CashBox, on_delete=models.CASCADE, related_name="movements")
    concept = models.ForeignKey(CashConcept, on_delete=models.PROTECT)
    method = models.CharField(max_length=10, choices=InvoicePayment.PAYMENT_METHODS)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Relación opcional con InvoicePayment
    invoice_payment = models.ForeignKey(
        InvoicePayment,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="cash_movements"
    )

    def __str__(self):
        return f"{self.cashbox} - {self.concept.name} - {self.total}"

class CashOutflow(models.Model):

    cashbox = models.ForeignKey(CashBox, on_delete=models.CASCADE, related_name="outflows")
    method = models.CharField(max_length=10, choices=InvoicePayment.PAYMENT_METHODS)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True, null=True)  # Ej. N° de depósito
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Egreso de caja"
        verbose_name_plural = "Egresos de caja"

    def __str__(self):
        return f"{self.cashbox} - {self.concept.name} - {self.total}"

class ReadingGeneration(models.Model):

    period = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    date_of_issue = models.DateField()
    date_of_due = models.DateField()
    date_of_cute = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reading_generations"
    )

    total_generated = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:

        unique_together = ("period",)  # solo se puede generar 1 vez por periodo
        ordering = ["-period"]

    def __str__(self):

        return f"Generación {self.period.strftime('%Y-%m')} ({self.total_generated} lecturas)"


 # class PaymentMethod(models.Model):

class Notificacion(models.Model):

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    mensaje = models.TextField()
    fecha = models.DateTimeField(auto_now_add=True)
    leido = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.usuario.username} - {self.mensaje[:30]}"

#     state = models.BooleanField(default=True)
#     description = models.CharField(max_length=200)

#     class Meta:

#         verbose_name_plural = "Tipo de metodo de pago"
#         verbose_name = "Tipos de metodos de pagos"

#     def __str__(self):

#         return self.description

# class Year(models.Model):

#     """
#     Representa un año (ej. 2025) para que el usuario seleccione en cuál trabajar.
#     Puedes añadir campos extra si quieres manejar más información.
#     """
#     year = models.PositiveSmallIntegerField(unique=True)
#     # Ejemplo: bandera para saber si está activo o cerrado
#     state = models.BooleanField(default=True)

#     def __str__(self):
#         return str(self.year)

#     class Meta:
#         ordering = ['year']
#         verbose_name = "Year Period"
#         verbose_name_plural = "Year Periods"