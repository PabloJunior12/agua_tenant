
from apps.base.models import BaseModel
from decimal import Decimal
from datetime import timedelta, date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import models, connection
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

    codigo = models.CharField(max_length=4, unique=True, editable=False)
    name = models.CharField(max_length=100, verbose_name="Nombre de la Zona")

    def save(self, *args, **kwargs):

        if not self.codigo:

            last_via = Zona.objects.order_by('-id').first()

            next_number = 1 if not last_via else int(last_via.codigo) + 1

            self.codigo = str(next_number).zfill(4)  # genera "01", "02", "03"...

        super().save(*args, **kwargs)



    class Meta:
        verbose_name = "Zona"
        verbose_name_plural = "Zonas"

    def __str__(self):

        return self.name

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
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT, null=True)

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
    
    MODE_CHOICES = [
        ('per_unit', 'Por consumo real'),
        ('fixed_until_max', 'Fijo hasta máximo'),
    ]

    codigo = models.CharField(max_length=2, null=True, blank=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    min_consumption = models.IntegerField(null=True, blank=True)  # Desde qué m³ aplica
    max_consumption = models.IntegerField(null=True, blank=True)

    extra_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    price_water = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de agua")
    price_sewer = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de alcantarillado")
    price_fixed_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    price_clean = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    billing_mode = models.CharField(
        max_length=20,
        choices=MODE_CHOICES,
        default='per_unit'
    )

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

    user_id = models.IntegerField()
    opening_date = models.DateTimeField(auto_now_add=True)
    closing_date = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="open")

    def __str__(self):

        return f"Caja {self.id}"

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

    SYSTEM_KEYS = (
        ("price_water", "Precio agua"),
        ("price_sewer", "Precio alcantarillado"),
        ("price_fixed_charge", "Precio cargo fijo"),
        ("price_clean", "Precio limpieza"),
        ("price_igv", "Precio Igv"),
    )

    code = models.CharField(max_length=3, unique=True, null=True, blank=True)
    name = models.CharField(max_length=150)
    type = models.CharField(max_length=15)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    is_master = models.BooleanField(default=False)
    is_master_view = models.BooleanField(default=False)
    state = models.BooleanField(default=True)

    system_key = models.CharField(
        max_length=30,
        choices=SYSTEM_KEYS,
        null=True,
        blank=True,
        db_index=True
    )

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

    CONNECTION_TYPE_NEW = 'new'
    CONNECTION_TYPE_OLD = 'old'

    CONNECTION_TYPES = [
        (CONNECTION_TYPE_NEW, 'Conexión nueva'),
        (CONNECTION_TYPE_OLD, 'Conexión antigua'),
    ]

    ESTADO_CHOICES = [
    
        # CHILCA Y PANGOA

        ("active", "Activo"),
    
        # PANGOA

        ("inactive", "Inactivo"),
        ("suspended", "Suspendido"),

        # CHILCA

        ("low", "Baja"),
        ("observed", "Observado"),
    ]

    BILLING_TYPE_CHOICES = [
        ('both', 'Agua y desagüe'),
        ('water', 'Solo agua'),
        ('sewer', 'Solo desagüe'),
    ]

    codigo = models.CharField(max_length=10, null=True, blank=True)
    
    identity_document_type = models.IntegerField(default=1)
    full_name = models.CharField(max_length=200)
    number = models.CharField(max_length=15, blank=True, null=True)  # Ya no unique
    address = models.CharField(max_length=255, null=True, blank=True)
    has_meter = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="customers")
    calle = models.ForeignKey(Calle, on_delete=models.PROTECT, null=True)
    zona = models.ForeignKey(Zona, on_delete=models.PROTECT, null=True)

    provincia = models.CharField(max_length=15, blank=True, null=True)
    distrito = models.CharField(max_length=15, blank=True, null=True)
    sector = models.CharField(max_length=15, blank=True, null=True)
    mz = models.CharField(max_length=15, blank=True, null=True)
    lote = models.CharField(max_length=15, blank=True, null=True)
    nro = models.CharField(max_length=15, blank=True, null=True)

    state = models.CharField(max_length=15, choices=ESTADO_CHOICES, default="active")

    # PANGOA

    connection_type = models.CharField(max_length=10, choices=CONNECTION_TYPES, default=CONNECTION_TYPE_NEW)

    # CHILCA

    supply_number = models.CharField(max_length=10, null=True, blank=True) # N° DE SUMINISTRO
    record_number = models.CharField(max_length=20, null=True, blank=True) # N° DE EXPEDIENTE
    date_of_record = models.DateField(null=True, blank=True)
    billing_type = models.CharField(max_length=10, choices=BILLING_TYPE_CHOICES, default='both')
    observation = models.TextField(null=True, blank=True) 

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

    # Usas este campo como "mes facturado"
    period = models.DateField()

    # Fechas automaticas
    date_of_issue = models.DateField(null=True)
    date_of_due = models.DateField(null=True)
    date_of_cute = models.DateField(null=True)

    # (Opcionales, si deseas registrarlos)
    period_start = models.DateField(null=True)
    period_end = models.DateField(null=True)

    current_reading = models.DecimalField(max_digits=10, decimal_places=3)
    previous_reading = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)
    consumption = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)

    igv = models.IntegerField(default=18)

    total_water = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_sewer = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_clean = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_fixed_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_igv = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    sub_total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) 
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
 
    paid = models.BooleanField(default=False)
    has_meter = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        unique_together = ('customer', 'period')
        ordering = ['-period']

    def __str__(self):

        return f"{self.customer.full_name} - {self.period.strftime('%Y-%m')}"

    def calcular_igv_simple(self, monto):
 
        igv = monto * Decimal('0.18')  # Usar Decimal, no float
        return round(igv, 2)

    # -------------------------------
    # Cálculos de consumo y tarifas
    # -------------------------------

    def calculate_per_unit_tariff(self, tariff):

        """
        Modo estándar:
        - Si NO hay max_consumption → todo por price_water
        - Si hay max_consumption → hasta el máximo a price_water
        y el exceso a extra_rate
        """

        consumo = self.consumption or Decimal('0.000')

        # Si no hay límite configurado
        if not tariff.max_consumption:
            return consumo * tariff.price_water

        # Hay límite
        maximo = tariff.max_consumption
        precio_base = tariff.price_water
        precio_extra = tariff.extra_rate or Decimal('0.00')

        consumo_base = min(consumo, maximo)
        exceso = max(consumo - maximo, Decimal('0.000'))

        return (consumo_base * precio_base) + (exceso * precio_extra)

    def calculate_fixed_until_max_tariff(self, tariff):

        """
        Fijo hasta máximo y luego extra por exceso
        """
        consumo = self.consumption or Decimal('0.000')
        fijo = tariff.price_water
        maximo = tariff.max_consumption or Decimal('0.000')
        extra = tariff.extra_rate or Decimal('0.00')

        if consumo <= maximo:

            return fijo
        
        else:

            exceso = consumo - maximo
            return fijo + (exceso * extra)

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
   
            self.consumption = Decimal(self.current_reading) - Decimal(self.previous_reading)

        else:
            # Sin medidor: todo fijo
            self.previous_reading = Decimal('0.000')
            self.consumption = Decimal('0.000')

    def calculate_total(self):

        tariff = self.customer.category
        config = Config.objects.first()

        tenant = connection.schema_name  # 👈 importante

        billing_type = (self.customer.billing_type or 'both')

        # Valores base
        water = Decimal('0.00')
        sewer = Decimal('0.00')

        # =========================
        # AGUA
        # =========================
        if tariff.has_meter:

            if tariff.billing_mode == 'per_unit':
                water = self.calculate_per_unit_tariff(tariff)

            elif tariff.billing_mode == 'fixed_until_max':
                water = self.calculate_fixed_until_max_tariff(tariff)

            else:
                water = self.consumption * tariff.price_water
        else:
            water = tariff.price_water

        # =========================
        # DESAGÜE
        # =========================
        sewer = tariff.price_sewer or Decimal('0.00')

        # =========================
        # 🎯 LÓGICA SOLO PARA CHILCA
        # =========================
        if tenant == "chilca":

            if billing_type == "water":
                sewer = Decimal('0.00')

            elif billing_type == "sewer":
                water = Decimal('0.00')

            # both = normal

        # =========================
        # ASIGNACIÓN FINAL
        # =========================
        self.total_water = water
        self.total_sewer = sewer
        self.total_fixed_charge = tariff.price_fixed_charge or Decimal('0.00')
        self.total_clean = tariff.price_clean or Decimal('0.00')

        subtotal = self.total_water + self.total_sewer

        if config.add_igv_category:
            self.total_igv = self.calcular_igv_simple(subtotal)
        else:
            self.total_igv = Decimal('0.00')

        self.sub_total_amount = subtotal + self.total_igv

        self.total_amount = (
            self.sub_total_amount +
            self.total_clean +
            self.total_fixed_charge
        )

        return self.total_amount

    def set_billing_dates(self):

        year = self.period.year
        month = self.period.month

        # Fecha de emision
        self.date_of_issue = date(year, month, 25)

        # Fecha de vencimiento (mes siguiente)
        if month == 12:
            self.date_of_due = date(year + 1, 1, 15)
        else:
            self.date_of_due = date(year, month + 1, 15)

        # Fecha de corte (7 dias despues)
        self.date_of_cute = self.date_of_due + timedelta(days=7)

        # Periodo de consumo exacto
        # Inicio: 25 del mes anterior
        if month == 1:
            self.period_start = date(year - 1, 12, 25)
        else:
            self.period_start = date(year, month - 1, 25)

        # Fin: 24 del mes actual
        self.period_end = date(year, month, 24)

    # -------------------------------
    # Sincronizacion con deudas
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

        concept_map = {
            "price_water": self.total_water,
            "price_sewer": self.total_sewer,
            "price_fixed_charge": self.total_fixed_charge,
            "price_clean": self.total_clean,
            "price_igv": self.total_igv,
        }

        concepts = CashConcept.objects.filter(
            system_key__in=concept_map.keys()
        )

        for concept in concepts:

            amount = concept_map.get(concept.system_key, 0)

            if amount > 0:

                DebtDetail.objects.create(
                    debt=debt,
                    concept=concept,
                    amount=amount
                )

    # -------------------------------
    # Guardado con cascada
    # -------------------------------

    def save(self, *args, skip_process=False, **kwargs):

        # Primero generamos fechas automaticas
        self.set_billing_dates()

        if not skip_process:

            # Calcular consumo + total de esta lectura
            self.calculate_consumption()
            self.calculate_total()

            # Guardar lectura actual
            super().save(*args, **kwargs)

            # Crear o actualizar deuda
            self._sync_debt()

            # Recalcular en cascada los meses posteriores
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

            # Guardar directo sin procesos
            super().save(*args, **kwargs)

class Debt(models.Model):
    
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="debts")
    period = models.DateField()  # Ej. 2025-02-01
    description = models.CharField(max_length=255, blank=True, null=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # suma de detalles
    paid = models.BooleanField(default=False)
    is_refinanced = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    reading = models.OneToOneField("Reading", on_delete=models.SET_NULL, null=True, blank=True, related_name="debt")

    class Meta:
        ordering = ['-period']
 
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

# CHILCA

class DebtRefinancing(models.Model):

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    paid = models.BooleanField(default=False)

class DebtRefinancingDetail(models.Model):

    refinancing = models.ForeignKey(
        DebtRefinancing,
        on_delete=models.CASCADE,
        related_name="details"
    )

    debt = models.ForeignKey(Debt, on_delete=models.PROTECT)

class RefinancingInstallment(models.Model):

    refinancing = models.ForeignKey(
        DebtRefinancing,
        on_delete=models.CASCADE,
        related_name="installments"
    )

    number = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    paid = models.BooleanField(default=False)

class CutBatch(models.Model):

    STATUS_CHOICES = [
        ("planned", "Planificado"),
        ("in_progress", "En ejecución"),
        ("completed", "Completado"),
    ]

    name = models.CharField(max_length=100)
    sector = models.CharField(max_length=50, null=True, blank=True)
    zone = models.CharField(max_length=50, null=True, blank=True)

    scheduled_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="planned")

    created_at = models.DateTimeField(auto_now_add=True)

class ServiceCut(models.Model):

    STATUS_CHOICES = [
        ("pending", "Pendiente"),
        ("executed", "Ejecutado"),
        ("cancelled", "Cancelado"),
    ]

    RESULT_CHOICES = [
        ("executed", "Cortado"),
        ("paid", "Pagó en campo"),
        ("not_found", "No ubicado"),
        ("postponed", "Postergado"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="cuts")
    debts = models.ManyToManyField(Debt, blank=True)

    batch = models.ForeignKey(
        CutBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cuts"
    )

    reason = models.CharField(max_length=255, default="Deuda pendiente")

    scheduled_date = models.DateField()
    execution_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    result = models.CharField(max_length=20, choices=RESULT_CHOICES, null=True, blank=True)

    executed_by = models.IntegerField(null=True, blank=True)
    observation = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.IntegerField(null=True, blank=True)

    def execute_cut(self, user_id=None, result="executed", observation=None):

        if self.status != "pending":
            return

        self.status = "executed"
        self.result = result
        self.execution_date = date.today()
        self.created_by = user_id
        self.executed_by = user_id
        self.observation = observation
        self.save()

        if result == "executed":
            self.customer.state = "low"
            self.customer.save()

# END CHILCA

class Invoice(models.Model):

    STATUS_CHOICES = [
        ('active', 'Activa'),
        ('cancelled', 'Anulada'),
    ]

    PAYMENT_ORIGIN_CHOICES = (
        ("counter", "Presencial"),
        ("gateway", "Pasarela de pagos"),
    )

    name_optional = models.CharField(max_length=200, blank=True, null=True)
    number_optional = models.CharField(max_length=15, blank=True, null=True)

    code = models.CharField(max_length=7, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    date = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reference = models.CharField(max_length=100, blank=True, null=True)  # N° operación bancaria, etc.
    number_reference = models.CharField(max_length=20, blank=True, null=True) 
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    payment_origin = models.CharField(
        max_length=20,
        choices=PAYMENT_ORIGIN_CHOICES,
        default="counter"
    )

    payment_reference = models.CharField(max_length=50, null=True, blank=True, unique=True)

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

class InvoiceInstallment(models.Model):

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name='invoice_installments'
    )

    installment = models.ForeignKey(
        RefinancingInstallment,
        on_delete=models.CASCADE
    )

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
    created_by = models.IntegerField(null=True, blank=True)
    total_generated = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, null=True)

    class Meta:

        unique_together = ("period",)  # solo se puede generar 1 vez por periodo
        ordering = ["-period"]

    def __str__(self):

        return f"Generación {self.period.strftime('%Y-%m')} ({self.total_generated} lecturas)"


 # class PaymentMethod(models.Model):

class Config(models.Model):

    add_igv_category = models.BooleanField(default=False, verbose_name="Incluir IGV en tarifas")

    # --- PASARELA DE PAGOS ---
    enable_online_payments = models.BooleanField(
        default=False,
        verbose_name="Habilitar pagos online"
    )

    mp_public_key = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Mercado Pago Public Key"
    )

    mp_access_token = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        verbose_name="Mercado Pago Access Token"
    )




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