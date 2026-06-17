from decimal import Decimal
from datetime import  date

from django.core.exceptions import ValidationError
from django.db import models, connection
from django.utils.timezone import now

from .utils import get_concept_total

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

class Manzana(models.Model):

    zona = models.ForeignKey(
        Zona,
        on_delete=models.CASCADE,
        related_name='manzanas'
    )

    codigo = models.CharField(
        max_length=10,
        verbose_name='Código'
    )

    class Meta:
        verbose_name = 'Manzana'
        verbose_name_plural = 'Manzanas'
        unique_together = ('zona', 'codigo')

    def __str__(self):
        return f"{self.zona.codigo} - {self.codigo}"

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

    # WATER

    price_water = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de agua")
    extra_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # SEWER

    price_sewer = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Precio de alcantarillado")
    extra_rate_sewer = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    min_consumption = models.IntegerField(null=True, blank=True)  # Desde qué m³ aplica
    max_consumption = models.IntegerField(null=True, blank=True)
   
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
        ("price_maintenance", "Precio Mantenimiento"),
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

class Customer(models.Model):

    CONNECTION_TYPE_NEW = 'new'
    CONNECTION_TYPE_OLD = 'old'

    CONNECTION_TYPES = [
        (CONNECTION_TYPE_NEW, 'Conexión nueva'),
        (CONNECTION_TYPE_OLD, 'Conexión antigua'),
    ]

    SOURCE_CHOICES_COMPANY = 'company'

    SOURCE_CHOICES = [
        ('well', 'Pozo'),
        ('company', 'Empresa'),
    ]

    ESTADO_CHOICES = [
    
        # CHILCA Y PANGOA

        ("active", "Activo"),
    
        # PANGOA

        ("inactive", "Inactivo"),
        ("suspended", "Suspendido"),

        # CHILCA

        ("cut", "Cortado"),
        ("low", "Baja"),
        
    ]

    BILLING_TYPE_CHOICES = [
        ('both', 'Agua y desagüe'),
        ('water', 'Solo agua'),
        ('sewer', 'Solo desagüe'),
    ]

    codigo = models.CharField(max_length=10, null=True, blank=True)
    
    identity_document_type = models.IntegerField(default=1)
    full_name = models.CharField(max_length=200)
    number = models.CharField(max_length=15, blank=True, null=True)
    address = models.CharField(max_length=255, null=True, blank=True)
    reference_address = models.CharField(max_length=255, null=True, blank=True)
    has_meter = models.BooleanField(default=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="customers")
    calle = models.ForeignKey(Calle, on_delete=models.PROTECT, null=True)
    
    zona = models.ForeignKey(
        Zona,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customers'
    )

    manzana = models.ForeignKey(
        Manzana,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customers'
    )

    provincia = models.CharField(max_length=15, blank=True, null=True)
    distrito = models.CharField(max_length=15, blank=True, null=True)

    sector = models.CharField(max_length=15, blank=True, null=True)
    mz = models.CharField(max_length=15, blank=True, null=True)
    predio = models.CharField(max_length=15, blank=True, null=True)

    lote = models.CharField(max_length=15, blank=True, null=True)
    nro = models.CharField(max_length=15, blank=True, null=True)

    state = models.CharField(max_length=15, choices=ESTADO_CHOICES, default="active")
    status = models.BooleanField(default=True)

    phone = models.CharField(max_length=15, blank=True, null=True)

    # PANGOA

    connection_type = models.CharField(max_length=10, choices=CONNECTION_TYPES, default=CONNECTION_TYPE_NEW)

    # CHILCA

    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_CHOICES_COMPANY)
    supply_number = models.CharField(max_length=10, null=True, blank=True) # N° DE SUMINISTRO
    record_number = models.CharField(max_length=20, null=True, blank=True) # N° DE EXPEDIENTE
    date_of_record = models.DateField(null=True, blank=True)
    billing_type = models.CharField(max_length=10, choices=BILLING_TYPE_CHOICES, default='both')
    observation = models.TextField(null=True, blank=True) 

    def __str__(self):

        return f"{self.full_name} ({self.number or 'sin DNI'})"

class WaterMeter(models.Model):

    STATUS_CHOICES = [
        ('available', 'Disponible'),
        ('installed', 'Instalado'),
        ('removed', 'Retirado'),
        ('damaged', 'Dañado'),
        ('maintenance', 'Mantenimiento'),
    ]

    code = models.CharField(max_length=50, unique=True)
    brand = models.CharField(max_length=50, null=True, blank=True)
    model = models.CharField(max_length=50, null=True, blank=True)
    diameter = models.CharField(max_length=10, null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')

    purchase_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.code} ({self.status})"

class MeterAssignment(models.Model):

    meter = models.ForeignKey(WaterMeter, on_delete=models.CASCADE, related_name="assignments")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    installation_date = models.DateField()
    removal_date = models.DateField(null=True, blank=True)

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.meter.code} → {self.customer.full_name}" 

class Reading(models.Model):
    
    READING_STATUS = (
        ('normal', 'Normal'),
        ('estimated', 'Estimada'),
        ('revised', 'Corregida'),
        ('no_access', 'Sin acceso'),
    )

    customer = models.ForeignKey('Customer', related_name='readings', on_delete=models.CASCADE)

    meter = models.ForeignKey(WaterMeter, on_delete=models.SET_NULL, null=True, blank=True)

    period = models.DateField()

    # Fechas automaticas
    date_of_issue = models.DateField(null=True)
    date_of_due = models.DateField(null=True)
    date_of_cute = models.DateField(null=True)

    current_reading = models.DecimalField(max_digits=10, decimal_places=3)
    previous_reading = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)
    consumption = models.DecimalField(max_digits=10, decimal_places=3, default=0.000)

    status = models.CharField(max_length=20, choices=READING_STATUS, default='normal')
    observation = models.TextField(blank=True, null=True)

    total_water = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_sewer = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

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

    # -------------------------------
    # Cálculos de consumo y tarifas
    # -------------------------------

    def calculate_water_total(self, tariff):

        """
        Modo estándar:
        - Si NO hay max_consumption → todo por price_water
        - Si hay max_consumption → hasta el máximo a price_water
        y el exceso a extra_rate
        """

        consumo = self.consumption or Decimal('0.00')

        if not tariff.max_consumption:
            return consumo * tariff.price_water

        consumo_base = min(consumo, tariff.max_consumption)
        exceso = max(consumo - tariff.max_consumption, Decimal('0.00'))

        total = (
            (consumo_base * tariff.price_water)
            + (exceso * tariff.extra_rate)
        )

        return total

    def calculate_sewer_total(self, tariff):

        tenant = connection.schema_name

        consumo = self.consumption or Decimal('0.00')

        # =====================================
        # PANGOA → DESAGÜE FIJO
        # =====================================
        if tenant == "pangoa":

            return tariff.price_sewer or Decimal('0.00')

        # =====================================
        # CHILCA → DESAGÜE POR m3
        # =====================================
        elif tenant == "chilca":

            if tariff.max_consumption:

                consumo_base = min(consumo, tariff.max_consumption)

                exceso = max(
                    consumo - tariff.max_consumption,
                    Decimal('0')
                )

                return (
                    (consumo_base * tariff.price_sewer)
                    + (exceso * tariff.extra_rate_sewer)
                )

            return consumo * tariff.price_sewer

        # =====================================
        # DEFAULT
        # =====================================
        return tariff.price_sewer or Decimal('0.00')

    def calculate_water_total_fixed_until_max(self, tariff):

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

    def calculate_sewer_total_fixed_until_max(self, tariff):

        """
        Fijo hasta máximo y luego extra por exceso
        """
        consumo = self.consumption or Decimal('0.000')
        fijo = tariff.price_sewer
        maximo = tariff.max_consumption or Decimal('0.000')
        extra = tariff.extra_rate_sewer or Decimal('0.00')

        if consumo <= maximo:

            return fijo
        
        else:

            exceso = consumo - maximo

            # print(fijo + (exceso * extra))
            return fijo + (exceso * extra)

    # END CALCULO

    def calculate_consumption(self):

        if self.meter:

            # ✅ solo autocompletar si no enviaron previous_reading
            if Decimal(self.previous_reading or 0) <= 0:

                previous = Reading.objects.filter(
                    customer=self.customer,
                    period__lt=self.period
                ).order_by('-period').first()

                if previous:
                    self.previous_reading = previous.current_reading

            self.consumption = (
                Decimal(self.current_reading)
                - Decimal(self.previous_reading)
            )

        else:

            self.previous_reading = Decimal('0.000')
            self.consumption = Decimal('0.000')

    def calculate_total(self):

        tenant = connection.schema_name

        tariff = self.customer.category
        billing_type = (self.customer.billing_type or 'both')

        # Valores base
        water = Decimal('0.00')
        sewer = Decimal('0.00')

        # =========================
        # AGUA
        # =========================
        if tariff.has_meter:

            if tariff.billing_mode == 'per_unit':
              
                water = self.calculate_water_total(tariff)
                sewer = self.calculate_sewer_total(tariff)

            elif tariff.billing_mode == 'fixed_until_max':
                
                water = self.calculate_water_total_fixed_until_max(tariff)
                sewer = self.calculate_sewer_total_fixed_until_max(tariff)
            
            else:

                water = self.consumption * tariff.price_water
                sewer = tariff.price_sewer or Decimal('0.00')

        else:

            water = tariff.price_water
            sewer = tariff.price_sewer or Decimal('0.00')

    
        if billing_type == "water":

            sewer = Decimal('0.00')

        elif billing_type == "sewer":

            water = Decimal('0.00')
     
        if tenant == "pangoa":

            if self.customer.state == "inactive":

                water = Decimal("0.00")
                sewer = Decimal("0.00")

        # =========================
        # ASIGNACIÓN FINAL
        # =========================

        self.total_water = water
        self.total_sewer = sewer

        self.sub_total_amount = self.total_water + self.total_sewer
        self.total_amount = self.sub_total_amount 

        return self.total_amount

    # -------------------------------
    # Sincronizacion con deudas
    # -------------------------------

    def _sync_debt(self):

        from .models import Debt, DebtDetail, CashConcept

        normalized_period = date(self.period.year, self.period.month, 1)

        tenant = connection.schema_name

        price_clean = get_concept_total('price_clean')
        price_fixed_charge = get_concept_total('price_fixed_charge')
        price_maintenance = get_concept_total('price_maintenance')

        if tenant == "pangoa":

            if self.customer.state != "inactive":

               price_maintenance = 0

        total_amount = self.total_amount + price_clean + price_fixed_charge + price_maintenance

        debt, created = Debt.objects.get_or_create(
            customer=self.customer,
            period=normalized_period,
            defaults={
                "reading": self,
                "amount": total_amount,
                "description": "Deuda por consumo de agua/desagüe",
            }
        )

        if not created:

            if debt.paid:

                # 🔒 Si la deuda ya está pagada, no se puede modificar
                raise ValidationError(f"No se puede modificar la lectura de {self.period.strftime('%Y-%m')} porque ya está pagada.")
            
            debt.reading = self
            debt.amount = total_amount
            debt.save()

        # recreamos detalles
        debt.details.all().delete()

        concept_map = {

            "price_water": self.total_water,
            "price_sewer": self.total_sewer,

            "price_fixed_charge": price_fixed_charge,
            "price_clean": price_clean,
            "price_maintenance": price_maintenance,
        }

        concepts = {
            concept.system_key: concept
            for concept in CashConcept.objects.filter(
                system_key__in=concept_map.keys()
            )
        }


        for system_key, amount in concept_map.items():

            if amount > 0:

                DebtDetail.objects.create(
                    debt=debt,
                    concept=concepts[system_key],
                    amount=amount
                )

    # -------------------------------
    # Guardado con cascada
    # -------------------------------

    def save(self, *args, skip_process=False, **kwargs):

        assignment = MeterAssignment.objects.filter(customer=self.customer, is_active=True).select_related('meter').first()

        if assignment:

            self.meter = assignment.meter
            self.has_meter = True

        else:

            self.has_meter = False

        if not skip_process:

            # Calcular consumo + total de esta lectura
            self.calculate_consumption()
            self.calculate_total()

            # Guardar lectura actual
            super().save(*args, **kwargs)

            # Crear o actualizar deuda
            self._sync_debt()

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

    TYPE_CHOICES = (
        ('debt', 'Deuda'),
        ('service', 'Servicio')
    )

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='debt'
    )

    customer = models.ForeignKey(Customer,on_delete=models.CASCADE, related_name="refinancings")

    # deuda original
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # 0.20% por cuota
    interest_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.20
    )

    # interés total generado
    interest_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # total final refinanciado
    total_amount_with_interest = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # cantidad de cuotas
    installments = models.IntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)

    paid = models.BooleanField(default=False)

    initial_payment = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    original_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

class RefinancingInstallment(models.Model):

    refinancing = models.ForeignKey(
        DebtRefinancing,
        on_delete=models.CASCADE,
        related_name="installment_details"
    )

    # número cuota
    number = models.IntegerField()

    # capital sin interés
    capital_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # interés cuota
    interest_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    # total cuota
    total_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    # fecha vencimiento
    due_date = models.DateField()

    paid = models.BooleanField(default=False)

class DebtRefinancingDetail(models.Model):

    refinancing = models.ForeignKey(
        DebtRefinancing,
        on_delete=models.CASCADE,
        related_name="details"
    )

    debt = models.ForeignKey(
        Debt,
        on_delete=models.PROTECT,
        null=True,
        blank=True
    )

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

    REFERENCE_CHOICES = (
        ('debt', 'Servicio de Agua'),
        ('concept', 'Cargo por Concepto'),
        ('fractionate', 'Cuota de Fraccionamiento'),
    )

    name_optional = models.CharField(max_length=200, blank=True, null=True)
    number_optional = models.CharField(max_length=15, blank=True, null=True)

    code = models.CharField(max_length=7, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='invoices')
    date = models.DateField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    reference = models.CharField(max_length=100, choices=REFERENCE_CHOICES, default='debt')
    number_reference = models.CharField(max_length=20, blank=True, null=True) 
    notes = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    user_id = models.IntegerField()

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

        # liberar cargos adicionales
        self.invoice_service_charges.update(
            status='pending',
            invoice=None
        )

        # Liberar cuotas de fraccionamiento
        for invoice_installment in self.invoice_installments.select_related(
            'installment',
            'installment__refinancing'
        ):

            installment = invoice_installment.installment

            installment.paid = False
            installment.save()

            refinancing = installment.refinancing

            # Si se anuló una cuota, el refinanciamiento ya no puede estar pagado
            refinancing.paid = False
            refinancing.save()


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

class ServiceCharge(models.Model):

    STATUS_CHOICES = (
        ('pending', 'Pendiente'),
        ('refinanced', 'Refinanciado'),
        ('paid', 'Pagado'),
    )

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='invoice_service_charges', null=True , blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)

    concept = models.ForeignKey(
        CashConcept,
        on_delete=models.PROTECT
    )

    is_refinanced = models.BooleanField(default=False)
    description = models.CharField(max_length=255)

    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)

class ServiceRefinancingDetail(models.Model):

    refinancing = models.ForeignKey(
        DebtRefinancing,
        on_delete=models.CASCADE,
        related_name="service_details"
    )

    service_charge = models.ForeignKey(
        ServiceCharge,
        on_delete=models.PROTECT
    )