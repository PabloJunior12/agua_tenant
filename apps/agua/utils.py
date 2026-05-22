import datetime
import django_filters
import pandas as pd
import uuid
import re
from django.db import transaction
from django.db.models import Max, IntegerField, Sum, Count, Min, Q, Prefetch, Exists, OuterRef, Subquery, DecimalField
from django.utils.timezone import now, localdate
from datetime import date
from decimal import Decimal, InvalidOperation
from .models import Reading, MeterAssignment, Debt, DailyCashReport, CashBox, WaterMeter, ServiceCut, Customer, Calle
from django.db.models.functions import Cast

MESES = {
    "ENERO": 1,
    "FEBRERO": 2,
    "MARZO": 3,
    "ABRIL": 4,
    "MAYO": 5,
    "JUNIO": 6,
    "JULIO": 7,
    "AGOSTO": 8,
    "SETIEMBRE": 9,
    "SEPTIEMBRE": 9,  # por si acaso
    "OCTUBRE": 10,
    "NOVIEMBRE": 11,
    "DICIEMBRE": 12,
}


VIAS_VALIDAS = ["AV", "JR", "CALLE", "PJE", "PRLG", "SECTOR", "AUTOP","PSJE"]

def extraer_via_y_nombre(address):
    if not address:
        return None, None

    address = address.upper()

    # Crear patrón dinámico con tus vías
    vias_pattern = "|".join(VIAS_VALIDAS)

    pattern = rf"\b({vias_pattern})\.?\s+([A-ZÁÉÍÓÚÑ\s]+)"

    match = re.search(pattern, address)

    if match:
        via = match.group(1).strip()
        nombre = match.group(2).strip()

        # limpiar espacios extras
        nombre = re.split(r"\s{2,}|\d", nombre)[0].strip()

        return via, nombre

    return None, None

def obtener_calle(address):

    via_str, nombre = extraer_via_y_nombre(address)

    if not via_str or not nombre:
        return None

    return Calle.objects.filter(name__iexact=nombre).first() or None

def obtener_billing_type(agua, desague):
    tiene_agua = agua == "A"
    tiene_desague = desague == "D"

    if tiene_agua and tiene_desague:
        return 'both'
    elif tiene_agua:
        return 'water'
    elif tiene_desague:
        return 'sewer'

    return 'both'

def next_month_date(date_obj):
    """Devuelve la fecha correspondiente al siguiente mes, con día=1."""
    year = date_obj.year
    month = date_obj.month + 1
    if month > 12:
        month = 1
        year += 1
    # Si tus lecturas siempre se guardan con day=1, puedes forzarlo a 1:
    return datetime.date(year, month, 1)

def flatten_errors(error_dict):
    """
    Convierte errores del serializer en un string plano legible.
    Compatible con errores anidados.
    """
    if isinstance(error_dict, dict):
        messages = []
        for field, errors in error_dict.items():
            if isinstance(errors, list):
                for error in errors:
                    messages.append(f"{field}: {error}")
            elif isinstance(errors, dict):
                nested = flatten_errors(errors)
                messages.append(f"{field}: {nested}")
            else:
                messages.append(f"{field}: {errors}")
        return ' | '.join(messages)
    elif isinstance(error_dict, list):
        return ' | '.join(str(e) for e in error_dict)
    return str(error_dict)

class ReadingFilter(django_filters.FilterSet):

    year = django_filters.NumberFilter(field_name='period', lookup_expr='year')
    month = django_filters.NumberFilter(field_name='period', lookup_expr='month')

    class Meta:
        
        model = Reading
        fields = ['customer', 'paid', 'year', 'month']

class DebtFilter(django_filters.FilterSet):

    year = django_filters.NumberFilter(field_name='period', lookup_expr='year')
    month = django_filters.NumberFilter(field_name='period', lookup_expr='month')

    class Meta:
        
        model = Debt
        fields = ['customer', 'paid','is_refinanced', 'year', 'month', 'customer__codigo']

def clean_value(value):
    if pd.isna(value):
        return None
    
    # Si es número (ej: 5.0 → 5)
    if isinstance(value, (int, float)):
        return str(int(value))
    
    # Si ya es string
    return str(value).strip()

def to_none_if_empty(value):
    """
    Convierte el valor a None si está vacío, es NaN o solo contiene espacios.
    Caso contrario, devuelve el string sin espacios.
    """
    if pd.isna(value):  # Detecta NaN de pandas
        return None
    value_str = str(value).strip()
    return value_str if value_str else None

def to_none_if_empty_has_meter(value):
    
    if pd.isna(value):
        return None
    value_str = str(value).strip().lower()
    return value_str if value_str else None

def to_decimal_or_none(value):
    """
    Convierte un valor a Decimal si es posible, 
    o devuelve None si está vacío, es NaN o no es convertible.
    """
    if value is None:
        return None
    if str(value).strip() == "" or str(value).strip().lower() == "nan":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    
def generar_periodos(anio, meses_texto):

    texto = (meses_texto or "").upper().strip()

    # quitar "DE"
    if texto.startswith("DE "):
        texto = texto[3:].strip()

    # normalizar espacios
    texto = " ".join(texto.split())

    # casos como "ENERO A"
    if texto.endswith(" A"):
        inicio_txt = texto.replace(" A", "").strip()
        fin_txt = inicio_txt

    elif " A " in texto:
        inicio_txt, fin_txt = texto.split(" A ", 1)
        inicio_txt = inicio_txt.strip()
        fin_txt = fin_txt.strip()

    else:
        inicio_txt = texto
        fin_txt = texto

    mes_inicio = MESES.get(inicio_txt)
    mes_fin = MESES.get(fin_txt)

    if not mes_inicio or not mes_fin:
        raise ValueError(f"Mes invalido: '{texto}'")

    periodos = []

    for mes in range(mes_inicio, mes_fin + 1):
        periodos.append(date(anio, mes, 1))

    return periodos

def format_period(periodo):
        
        year = periodo.year
        month = periodo.month
        meses = [
            "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"
        ]
        return f"{meses[month-1]} {year}"

def generate_daily_report(cashbox: CashBox, date=None):
    if not date:
        date = localdate()

    # saldo de ayer
    previous_report = DailyCashReport.objects.filter(
        cashbox=cashbox, date__lt=date
    ).order_by("-date").first()
    opening_balance = previous_report.closing_balance if previous_report else cashbox.opening_balance

    # ingresos y egresos del día
    movimientos = cashbox.movements.filter(created_at__date=date)
    total_incomes = movimientos.filter(concept__type="income").aggregate(s=Sum("total"))["s"] or 0
    # total_outcomes = movimientos.filter(concept__type="outcome").aggregate(s=Sum("total"))["s"] or 0

    # ✅ Egresos del día (CashOutflow)
    total_outcomes = (
        cashbox.outflows.filter(created_at__date=date)
        .aggregate(s=Sum("total"))["s"]
        or 0
    )

    closing_balance = opening_balance + total_incomes - total_outcomes

    report, created = DailyCashReport.objects.get_or_create(
        cashbox=cashbox,
        date=date,
        defaults={
            "opening_balance": opening_balance,
            "total_incomes": total_incomes,
            "total_outcomes": total_outcomes,
            "closing_balance": closing_balance,
        }
    )

    if not created:
        # si ya existe, actualizar montos
        report.opening_balance = opening_balance
        report.total_incomes = total_incomes
        report.total_outcomes = total_outcomes
        report.closing_balance = closing_balance
        report.save()

    return report

def get_reading_status(reading):

    today = date.today()

    if reading.paid:

        return "PAID"

    if today < reading.date_of_due:

        return "ON_TIME"

    if reading.date_of_due <= today < reading.date_of_cute:

        return "OVERDUE"

    if today >= reading.date_of_cute:
        
        return "CUT"

    return "UNKNOWN"

def generar_codigo_medidor_unico():

    while True:
        # Genera un código aleatorio (ej: MED-5f2e1a8d)
        nuevo_codigo = "MED-" + uuid.uuid4().hex[:8]

        # Verificar si ya existe
        if not WaterMeter.objects.filter(code=nuevo_codigo).exists():
            return nuevo_codigo
        
def calcular_igv_simple(monto):
 
        igv = monto * Decimal('0.18')  # Usar Decimal, no float
        return round(igv, 2)

def procesar_pago(payment):

    if payment["status"] != "approved":
        return

    # payment_id = str(payment["id"])

    # # idempotencia
    # if Pago.objects.filter(payment_id=payment_id).exists():
    #    return
 
    # with transaction.atomic():

    #     # guardar pago
    #     Pago.objects.create(
           
    #         payment_id=payment_id,
    #         status=payment["status"],
    #         payment_method=payment["payment_method_id"],
    #         amount=payment["transaction_amount"],
    #         raw=payment
    #     )

        # cerrar recibo
      
def calcular_igv_simple(monto):
 
    igv = monto * Decimal('0.18')  # Usar Decimal, no float
    return round(igv, 2)

def get_morosos_queryset(zona_id=None, min_months=1, state=None):

    pending_cut_subquery = ServiceCut.objects.filter(
        customer=OuterRef('pk'),
        status="pending"
    )

    executed_cut_subquery = ServiceCut.objects.filter(
        customer=OuterRef('pk'),
        status="executed"
    )

    queryset = (
        Customer.objects
        .annotate(
            unpaid_months=Count(
                'debts__id',
                filter=Q(debts__paid=False),
                distinct=True
            ),
            total_debt=Sum(
                'debts__amount',
                filter=Q(debts__paid=False)
            ),
            has_pending_cut=Exists(pending_cut_subquery),
            has_executed_cut=Exists(executed_cut_subquery),
        )
    )

    queryset = queryset.filter(unpaid_months__gte=min_months)

    # filtro dinámico de estado
    if state == 'active':
        queryset = queryset.filter(state='active')

    if zona_id:
        queryset = queryset.filter(zona_id=zona_id)

    return queryset

def get_catastral_queryset(period_date):

    previous_reading_qs = (
        Reading.objects
        .filter(
            customer=OuterRef('customer'),
            period__lt=period_date
        )
        .order_by('-period')
    )

    current_period_qs = (
        Reading.objects
        .filter(
            customer=OuterRef('customer'),
            period=period_date
        )
    )

    return (
        MeterAssignment.objects
        .select_related(
            'customer',
            'meter'
        )
        .filter(
            customer__state__in=['active'],
        )
        .annotate(

            mz_number=Cast(
                'customer__manzana__codigo',
                IntegerField()
            ),

            predio_number=Cast(
                'customer__predio',
                IntegerField()
            ),

            # anterior
            previous_reading=Subquery(
                previous_reading_qs.values('current_reading')[:1],
                output_field=DecimalField()
            ),

            previous_consumption=Subquery(
                previous_reading_qs.values('consumption')[:1],
                output_field=DecimalField()
            ),

            previous_period=Subquery(
                previous_reading_qs.values('period')[:1]
            ),

            # actual
            has_current_reading=Subquery(
                current_period_qs.values('id')[:1]
            ),

            current_reading_value=Subquery(
                current_period_qs.values('current_reading')[:1],
                output_field=DecimalField()
            ),

            current_consumption=Subquery(
                current_period_qs.values('consumption')[:1],
                output_field=DecimalField()
            ),

            current_observation=Subquery(
                current_period_qs.values('observation')[:1]
            ),

        )
        .order_by(
            'customer__sector',
            'mz_number',
            'predio_number'
        )
    )

def get_full_catastral_queryset():

    active_meter = MeterAssignment.objects.filter(
        customer=OuterRef('pk'),
        is_active=True
    )

    return (
        Customer.objects
        .select_related(
            'category',
            'zona',
            'manzana'
        )
        .annotate(
            mz_number=Cast(
                'manzana__codigo',
                IntegerField()
            ),

            predio_number=Cast(
                'predio',
                IntegerField()
            ),

            meter_code=Subquery(
                active_meter.values('meter__code')[:1]
            ),

            meter_id=Subquery(
                active_meter.values('meter_id')[:1]
            )
        )
        .order_by(
            'sector',
            'mz_number',
            'predio_number',
        )
    )