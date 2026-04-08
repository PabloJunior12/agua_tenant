from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from django.template.loader import render_to_string, get_template
from django.http import HttpResponse
from django.conf import settings
from django.utils.timezone import now, localdate

from django.db import transaction, connection
from django.db.models import Max, Sum, Count, Min, Q, Prefetch

from rest_framework.views import APIView
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView

from datetime import datetime, date, timedelta
from weasyprint import HTML
from collections import defaultdict
from babel.dates import format_date
from decimal import Decimal
from apps.tenant.models import Pay
from apps.user.models import User
from .models import Customer, Config, DailyCashReport, DebtRefinancing, DebtRefinancingDetail, RefinancingInstallment, WaterMeter, CashOutflow, CashBox, Reading, DebtDetail, CashConcept, Invoice, Category, Via, Calle, InvoiceDebt, InvoicePayment, Zona, Debt, ReadingGeneration, Company
from .serializers import (
    CustomerSerializer, MorosidadSerializer, WaterMeterSerializer, RefinancingInstallmentSerializer, ViaSerializer, CompanySerializer, CashOutflowSerializer, CalleSerializer, DebtSerializer, CashBoxSerializer, CustomerWithDebtsSerializer,
    ReadingSerializer,  InvoiceSerializer, CategorySerializer, ZonaSerializer, ConfigSerializer, ReadingGenerationSerializer, CashConceptSerializer, DailyCashReportSerializer)
from apps.agua.core.permissions import GlobalPermissionMixin, TenantPaymentCreatePermission

import io
import pandas as pd
import os
import zipfile
import uuid

from .utils import calcular_igv_simple, ReadingFilter, DebtFilter, to_none_if_empty, clean_value, to_none_if_empty_has_meter, to_decimal_or_none, generar_periodos, format_period, generate_daily_report, generar_codigo_medidor_unico, procesar_pago
from .core.mixins import TenantSafeMixin
import mercadopago

class CustomPagination(PageNumberPagination):

    page_size = 5  # Número de registros por página
    page_size_query_param = 'page_size'  # Permite cambiar el tamaño desde la URL
    max_page_size = 100  # Tamaño máximo permitido

class CustomerViewSet(TenantSafeMixin, GlobalPermissionMixin, viewsets.ModelViewSet):

    queryset = Customer.objects.all().order_by('-codigo')
    serializer_class = CustomerSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend,filters.SearchFilter]
    search_fields = ['codigo', 'full_name', 'number']

    filterset_fields = ['codigo','zona','calle']  

    def create(self, request, *args, **kwargs):

        data = request.data
        has_meter = data.get('has_meter', True)
        meter_data = data.get('meter', None)

        tenant = request.tenant.schema_name

        code_number = 10
        next_code_fixed = "0000000001"

        if tenant == 'pangoa' or tenant == 'chilca':

           code_number = 5
           next_code_fixed = "00001"

        elif tenant == 'sanmarcos':

           code_number = 8
           next_code_fixed = "00000001"
        
        try:
            # Validar duplicado de número si no tiene medidor
            # if not has_meter and data.get('number'):
            #     if Customer.objects.filter(number=data['number']).exists():
            #         return Response(
            #             {'error': 'Ya existe un cliente con este numero.'},
            #             status=status.HTTP_400_BAD_REQUEST
            #         )

            # Validar medidor antes de guardar el Customer
            if has_meter:
                if not meter_data:
                    return Response(
                        {'error': 'Este campo es obligatorio cuando el cliente tiene medidor.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                if WaterMeter.objects.filter(code=meter_data.get('code')).exists():
                    return Response(
                        {'error': 'Este codigo de medidor ya existe.'},
                        status=status.HTTP_400_BAD_REQUEST
                    )

            with transaction.atomic():
                # Obtener último código y sumar 1
                last_code = Customer.objects.aggregate(max_code=Max('codigo'))['max_code']
                if last_code:
                    next_code = str(int(last_code) + 1).zfill(code_number)
                else:
                    next_code = next_code_fixed

                # Asignar el nuevo código al cliente
                data['codigo'] = next_code

                customer_serializer = CustomerSerializer(data=data)
                customer_serializer.is_valid(raise_exception=True)
                customer = customer_serializer.save()

                if has_meter:
                    WaterMeter.objects.create(
                        customer=customer,
                        code=meter_data['code'],
                        installation_date=meter_data['installation_date']
                    )

                return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
  
    def update(self, request, *args, **kwargs):

        self.required_action = "edit"
        self.check_global_permission(request)

        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):

        # Validar permiso global para eliminar
        self.required_action = "delete"
        self.check_global_permission(request)

        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def next_codigo(self, request):
        last = Customer.objects.aggregate(max_codigo=Max('codigo'))

        if last['max_codigo']:
            next_num = int(last['max_codigo']) + 1
        else:
            next_num = 1

        codigo = str(next_num).zfill(5)

        return Response({"codigo": codigo})

    @action(detail=False, methods=['get'])
    def supply_number(self, request):
        last = Customer.objects.aggregate(max_codigo=Max('supply_number'))

        if last['max_codigo']:
            next_num = int(last['max_codigo']) + 1
        else:
            next_num = 1

        codigo = str(next_num).zfill(5)

        return Response({"supply_number": codigo})

    @action(detail=False, methods=["get"], url_path="by-code")
    def by_code_and_dni(self, request):
        codigo = request.query_params.get("codigo")
        # dni = request.query_params.get("dni")
        #  or not dni
        if not codigo:
            return Response(
                {"error": "Debe proporcionar codigo de suministro"},
                status=status.HTTP_400_BAD_REQUEST
            )
        # , number=dni
        try:
            customer = Customer.objects.get(codigo=codigo)
        except Customer.DoesNotExist:
            return Response(
                {"error": "Cliente no encontrado"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = CustomerWithDebtsSerializer(customer)
        return Response(serializer.data)
    
    @action(detail=False, methods=['post'])
    def import_excel(self, request):

        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(
                file,
                engine='openpyxl',
                # header=2,
                dtype={'Codigo': str}
            )
        except Exception as e:
            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # Obtenemos la zona por defecto (sin zona)
        default_zona = Zona.objects.first()
        # df = df.head(5)

        for index, row in df.iterrows():

            codigo = str(row.get('Codigo')).strip()
            if codigo:
               codigo = codigo[-5:]

            # DNI/RUC
            number = to_none_if_empty(row.get('DNI/RUC.'))

            identity_document_type = 0

            if number and number.isdigit():
                if len(number) == 8:
                    identity_document_type = 1  # DNI
                elif len(number) == 11:
                    identity_document_type = 6  # RUC
            else:
                number = "00000000"  # Valor por defecto si está vacío o no es válido

            full_name = to_none_if_empty(row.get('Usuario/Cliente'))
           
            calle_dir = row.get('cod_direc')
          
            zona_name = to_none_if_empty(row.get('Barrio'))
            
            nro = to_none_if_empty(row.get("Nro."))
            mz = to_none_if_empty(row.get("Mzna."))
            lote = to_none_if_empty(row.get("Lote"))


            if zona_name:

                zona_name = zona_name.strip().upper()
                zona = Zona.objects.filter(name__iexact=zona_name).first()
                if not zona:
                    zona = default_zona
            else:

                zona = default_zona

            # Normalizar valor
            if not calle_dir or str(calle_dir).strip() == '' or pd.isna(calle_dir):

                calle_dir = 1

            else:

                calle_dir = int(str(calle_dir).strip())


            calle_dir_ = str(calle_dir).zfill(4)

            calle = Calle.objects.filter(codigo=calle_dir_).first()

            # Si no existe, tomar la primera calle de toda la tabla
            if not calle:
                calle = Calle.objects.first()

            parts = [
                f"{calle.via.name} {calle.name}",
                f"Mz {mz}" if mz else None,
                f"Lt {lote}" if lote else None,
                f"N° {nro}" if nro else None,
            ]

            # eliminar None y unir
            address = " ".join([p for p in parts if p])
            # Medidor
            code = to_none_if_empty(row.get('Cod.Medidor'))
            tiene_medidor_excel = to_none_if_empty_has_meter(row.get('T.Med.'))

            if tiene_medidor_excel == "si":
                has_meter = True
            elif tiene_medidor_excel == "no":
                has_meter = False
            else:
                has_meter = True if code else False

            # Si tiene medidor pero no tiene código, generar uno
            if has_meter and not code:
               code = generar_codigo_medidor_unico()

            # Categoría
            category_id = to_none_if_empty(row.get('cod_categ')) or 1
            category_id_ = str(category_id).zfill(2)
            category = Category.objects.filter(codigo=category_id_).first()
      
            #Crear cliente
            customer = Customer.objects.create(
                codigo=codigo,
                identity_document_type=identity_document_type,
                full_name=full_name,
                number=number,
                address=address,
                nro=nro,
                mz=mz,
                lote=lote,
                has_meter=has_meter,
                category=category,
                calle = calle,
                zona = zona
            )

            # Crear medidor solo si aplica y no existe
            if has_meter and code:
                if not WaterMeter.objects.filter(code=code).exists():
                    WaterMeter.objects.create(
                        customer=customer,
                        code=code,
                        installation_date=now()
                    )

        return Response({"message": "Clientes importados correctamente"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def import_excel_(self, request):

        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(
                file,
                engine='openpyxl',
                dtype={'c_codigo': str}
            )
        except Exception as e:
            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        for index, row in df.iterrows():

            codigo = str(row.get('c_codigo')).strip()
            supply_number = str(row.get('c_codigo')).strip()

            provincia = clean_value(row.get("cr1"))
            distrito = clean_value(row.get("cr2"))
            sector = clean_value(row.get("cr3"))
            mz = clean_value(row.get("cr4"))
            lote = clean_value(row.get("cr5"))

            if codigo:
               codigo = codigo[-4:]
            
            customer = Customer.objects.get(codigo=f"0{codigo}")
            customer.supply_number = supply_number
            customer.provincia = provincia
            customer.distrito = distrito
            customer.sector = sector
            customer.mz = mz
            customer.lote = lote

            customer.save()

        return Response({"message": "Clientes importados correctamente"}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path='report/debt')
    def report(self,request):

        calle_id = request.query_params.get("calle")
        zona_id = request.query_params.get("zona")

        debts = Debt.objects.filter(paid=False)

        data = []

        total_general = Decimal("0.00")
        customers = Customer.objects.all()

        calle = None
        zona = None
        if calle_id:

            calle = Calle.objects.get(pk=calle_id)
            customers = customers.filter(calle_id=calle_id)

        if zona_id:

            zona = Zona.objects.get(pk=zona_id)
            customers = customers.filter(zona_id=zona_id)

        for customer in customers:

            customers_debts = debts.filter(customer=customer)

            if not customers_debts.exists():

               continue
               
            sumary = customers_debts.aggregate(
                total=Sum("amount"),
                min_period=Min("period"),
                max_period=Max("period")
            )

            total_general += sumary["total"] or Decimal("0.00")

            data.append({

                "customer" : customer,
                "min_period" : sumary["min_period"],
                "max_period" : sumary["max_period"],
                "total" : sumary["total"]

            })
     

        html_string = render_to_string("customer/report.html",{

            "data":data,
            "total_general":total_general,
            "date":datetime.now(),
            "calle": calle,
            "zona": zona

        })

        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'filename="reporte_global_deudas.pdf"'
        return response

    @action(detail=True, methods=['get'], url_path='report/debt-history')
    def report_debt_history(self, request, pk=None, **kwargs):
        customer = self.get_object()
        debts = customer.debts.all().order_by('period')

        # Agrupar deudas por año
        debts_by_year = defaultdict(list)
        for debt in debts:
            debts_by_year[debt.period.year].append(debt)

        total_debt = debts.aggregate(Sum('amount'))['amount__sum'] or 0
        total_paid = debts.filter(paid=True).aggregate(Sum('amount'))['amount__sum'] or 0
        total_pending = total_debt - total_paid

        html_string = render_to_string('customer/customer_debt_history.html', {
            'customer': customer,
            'debts_by_year': dict(sorted(debts_by_year.items())),
            'total_debt': total_debt,
            'total_paid': total_paid,
            'total_pending': total_pending,
            'today': datetime.now(),
        })

        pdf = HTML(string=html_string).write_pdf()
        filename = f"Historial_{customer.full_name.replace(' ', '_')}.pdf"
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="{filename}"'
        return response
    
class CashBoxViewSet(TenantSafeMixin,viewsets.ModelViewSet):
    
    queryset = CashBox.objects.all()
    serializer_class = CashBoxSerializer

    @action(detail=True, methods=["post"], url_path='close-cash')
    def confirm_daily_report(self, request, pk=None):
        cashbox = self.get_object()
        date = request.data.get("date") or str(localdate())

        report = generate_daily_report(cashbox, date)
        report.confirmed = True
        report.save()

        return Response({"message": f"Caja del {report.date} confirmada", "closing_balance": report.closing_balance})

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None, **kwargs):

        cashbox = self.get_object()
        user = User.objects.filter(id=cashbox.user_id).first()
        # 📌 Filtros de fechas
        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")
        date_param = request.query_params.get("date")

        movimientos = cashbox.movements.all()
        egresos = cashbox.outflows.all()

        # SYSTEM_KEYS = (
        #     ("price_water", "Precio agua"),
        #     ("price_sewer", "Precio alcantarillado"),
        #     ("price_fixed_charge", "Precio cargo fijo"),
        #     ("price_clean", "Precio limpieza"),
        #     ("price_igv", "Precio Igv"),
        # )

        PERIOD_CONCEPTS = {
            "price_water",
            "price_sewer",
            "price_fixed_charge",
        }

        if start_date and end_date:

            try:
                start = datetime.strptime(start_date, "%Y-%m-%d").date()
                end = datetime.strptime(end_date, "%Y-%m-%d").date()
            except ValueError:
                return Response({"error": "Formato de fecha inválido (use YYYY-MM-DD)"}, status=400)

            movimientos = movimientos.filter(created_at__date__range=(start, end))
            egresos = egresos.filter(created_at__date__range=(start, end))
            reporte_tipo = f"Reporte entre {start} y {end}"

        else:

            if date_param:
                try:
                    fecha = datetime.strptime(date_param, "%Y-%m-%d").date()
                except ValueError:
                    return Response({"error": "Formato de fecha inválido (use YYYY-MM-DD)"}, status=400)
            else:
                fecha = localdate()

            movimientos = movimientos.filter(created_at__date=fecha)
            egresos = egresos.filter(created_at__date=fecha)
            reporte_tipo = f"Reporte diario - {fecha}"

        # ==========================
        # AGRUPACIÓN POR CONCEPTO
        # ==========================
        conceptos_dict = defaultdict(list)

        for mov in movimientos.select_related("concept", "invoice_payment__invoice__customer"):
            concepto = mov.concept.name
            conceptos_dict[concepto].append(mov)

        conceptos_data = []

        for concepto, movs in conceptos_dict.items():
            facturas_dict = {}

            for m in movs:
                inv = m.invoice_payment.invoice if m.invoice_payment else None

                if not inv or inv.status == "cancelled":
                    continue  # ignoramos facturas anuladas

                key = inv.id
                if key not in facturas_dict:
                    facturas_dict[key] = {
                        "code": inv.code,
                        "number_reference" : inv.number_reference,
                        "date": inv.date,
                        "cliente": inv.customer.full_name,
                        "cliente_codigo": inv.customer.codigo,
                        "direccion": inv.customer.address,
                        "pagos": defaultdict(float),
                        "total": 0,
                        "periodo": "",  # 👈 string vacío por defecto
                    }

                    # 📌 Solo calcular periodo si el concepto es 001, 002 o 003
                    if m.concept.system_key in PERIOD_CONCEPTS:

                        periodos = list(
                            inv.invoice_debts.select_related("debt")
                            .values_list("debt__period", flat=True)
                        )

                        if periodos:
                            periodos = sorted(periodos)
                            if len(periodos) == 1:
                                facturas_dict[key]["periodo"] = format_period(periodos[0])
                            else:
                                facturas_dict[key]["periodo"] = (
                                    f"{format_period(periodos[0])} - {format_period(periodos[-1])}"
                                )

                metodo = m.invoice_payment.method if m.invoice_payment else "Desconocido"
                facturas_dict[key]["pagos"][metodo] += float(m.total)
                facturas_dict[key]["total"] += float(m.total)

            # Convertir a lista
            facturas_list = []
            total_concepto = 0
            for f in facturas_dict.values():
                total_concepto += f["total"]
                f["pagos"] = dict(f["pagos"])  # pasar defaultdict a dict normal
                facturas_list.append(f)

            conceptos_data.append({
                "concepto": concepto,
                "total": total_concepto,
                "facturas": facturas_list,
            })

        total_general = sum(c["total"] for c in conceptos_data)

        # Agrupar por método de pago
        metodo_dict = defaultdict(list)
        for mov in movimientos.select_related("invoice_payment__invoice"):
            metodo_dict[mov.method].append(mov)

        metodo_data = []
        for metodo, movs in metodo_dict.items():

            total_metodo = sum([
                m.total if not (m.invoice_payment and m.invoice_payment.invoice.status == "cancelled") else 0
                for m in movs
            ])
            metodo_data.append({
                "metodo": dict(InvoicePayment.PAYMENT_METHODS).get(metodo, metodo),
                "total": total_metodo,
                "movimientos": movs
            })

        html_string = render_to_string("reports/caja/daily.html", {
            "cashbox": cashbox,
            "user" : user,
            "conceptos": conceptos_data,
            "total_general": total_general,
            "reporte_tipo": reporte_tipo,
            "metodos": metodo_data,
            "report": cashbox,
        })

        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'filename="reporte_caja_{cashbox.id}.pdf"'
        return response

class DailyCashReportViewSet(TenantSafeMixin,viewsets.ModelViewSet):
    
    queryset = DailyCashReport.objects.all().order_by('-date')
    serializer_class = DailyCashReportSerializer

    @action(detail=True, methods=["get"])
    def report(self, request, pk=None, **kwargs):

        daily_cash = self.get_object()

        cashbox = daily_cash.cashbox
        user = User.objects.filter(id=cashbox.user_id).first()
        fecha = daily_cash.date

        movimientos = cashbox.movements.filter(created_at__date=fecha)
        reporte_tipo = f"Reporte - {fecha}"

        # ==========================
        # AGRUPACIÓN POR CONCEPTO
        # ==========================
        conceptos_dict = defaultdict(list)

        PERIOD_CONCEPTS = {
            "price_water",
            "price_sewer",
            "price_fixed_charge",
        }

        for mov in movimientos.select_related("concept", "invoice_payment__invoice__customer"):
            concepto = mov.concept.name
            conceptos_dict[concepto].append(mov)

        conceptos_data = []

        for concepto, movs in conceptos_dict.items():
            facturas_dict = {}

            for m in movs:
                inv = m.invoice_payment.invoice if m.invoice_payment else None

                if not inv or inv.status == "cancelled":
                    continue  # ignoramos facturas anuladas

                key = inv.id
                if key not in facturas_dict:
                    facturas_dict[key] = {
                        "code": inv.code,
                        "number_reference" : inv.number_reference,
                        "date": inv.date,
                        "cliente": inv.customer.full_name,
                        "cliente_codigo": inv.customer.codigo,
                        "direccion": inv.customer.address,
                        "pagos": defaultdict(float),
                        "total": 0,
                        "periodo": "",  # 👈 string vacío por defecto
                    }

                    # 📌 Solo calcular periodo si el concepto es 001, 002 o 003
                    if m.concept.system_key in PERIOD_CONCEPTS:
                        periodos = list(
                            inv.invoice_debts.select_related("debt")
                            .values_list("debt__period", flat=True)
                        )

                        if periodos:
                            periodos = sorted(periodos)
                            if len(periodos) == 1:
                                facturas_dict[key]["periodo"] = format_period(periodos[0])
                            else:
                                facturas_dict[key]["periodo"] = (
                                    f"{format_period(periodos[0])} - {format_period(periodos[-1])}"
                                )

                metodo = m.invoice_payment.method if m.invoice_payment else "Desconocido"
                facturas_dict[key]["pagos"][metodo] += float(m.total)
                facturas_dict[key]["total"] += float(m.total)

            # Convertir a lista
            facturas_list = []
            total_concepto = 0
            for f in facturas_dict.values():
                total_concepto += f["total"]
                f["pagos"] = dict(f["pagos"])  # pasar defaultdict a dict normal
                facturas_list.append(f)

            conceptos_data.append({
                "concepto": concepto,
                "total": total_concepto,
                "facturas": facturas_list,
            })

        total_general = sum(c["total"] for c in conceptos_data)

        # Agrupar por método de pago
        metodo_dict = defaultdict(list)
        for mov in movimientos.select_related("invoice_payment__invoice"):
            metodo_dict[mov.method].append(mov)

        metodo_data = []
        for metodo, movs in metodo_dict.items():

            total_metodo = sum([
                m.total if not (m.invoice_payment and m.invoice_payment.invoice.status == "cancelled") else 0
                for m in movs
            ])
            metodo_data.append({
                "metodo": dict(InvoicePayment.PAYMENT_METHODS).get(metodo, metodo),
                "total": total_metodo,
                "movimientos": movs
            })

        html_string = render_to_string("reports/caja/daily.html", {
            "cashbox": cashbox,
            "user": user,
            "conceptos": conceptos_data,
            "total_general": total_general,
            "reporte_tipo": reporte_tipo,
            "metodos": metodo_data,
            "report": daily_cash,
        })

        pdf = HTML(string=html_string).write_pdf()
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'filename="reporte_caja_{cashbox.id}.pdf"'
        return response

class WaterMeterViewSet(TenantSafeMixin,viewsets.ModelViewSet):
    
    queryset = WaterMeter.objects.all()
    serializer_class = WaterMeterSerializer

class ReadingViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Reading.objects.all().order_by('period')
    serializer_class = ReadingSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = ReadingFilter

    def perform_update(self, serializer):
        instance = self.get_object()

        # 🔒 Bloqueo extra desde ViewSet
        if instance.paid:
            raise ValidationError(
                f"No se puede modificar la lectura de {instance.period.strftime('%Y-%m')} porque ya esta pagada."
            )

        return serializer.save()
    
    def perform_destroy(self, instance):

        # 🔒 No borrar si está pagada
        if instance.paid:
            raise ValidationError({"error": "No se puede eliminar una lectura que ya esta pagada."})

        # 🔒 No borrar si existen lecturas posteriores pagadas
        has_paid_next = Reading.objects.filter(
            customer=instance.customer,
            period__gt=instance.period,
            paid=True
        ).exists()
        if has_paid_next:
            raise ValidationError({"error": "No se puede eliminar porque existen lecturas posteriores ya pagadas."})

        customer = instance.customer
        period = instance.period

        # Eliminar deuda asociada si existe
        if hasattr(instance, "debt"):
            instance.debt.delete()

        # Guardamos todas las lecturas posteriores (ordenadas por fecha)
        next_readings = Reading.objects.filter(
            customer=customer,
            period__gt=period
        ).order_by("period")

        # Eliminamos la lectura actual
        instance.delete()

        # 🔄 Recalcular en cascada todas las lecturas posteriores
        prev_value = 0
        prev_reading = Reading.objects.filter(
            customer=customer,
            period__lt=period
        ).order_by("-period").first()
        if prev_reading:
            prev_value = prev_reading.current_reading

        for r in next_readings:
            r.previous_reading = prev_value
            r.consumption = r.current_reading - prev_value

            # Si existe deuda asociada, actualizamos el monto
            if hasattr(r, "debt"):
                r.debt.amount = r.consumption * r.customer.category.price_water
                r.debt.save()

            r.save()
            prev_value = r.current_reading

    @action(detail=False, methods=['get'], url_path='has-history/(?P<customer_id>[^/.]+)')
    def has_history(self, request, customer_id=None):
        
        exists = Reading.objects.filter(customer_id=customer_id).exists()
        return Response({'hasHistory': exists})

    @action(detail=False, methods=['post'])
    def import_excel(self, request):

        month_map = {
            "Lect.Ene": 1, "Lect.Feb": 2, "Lect.Mar": 3, "Lect.Abr": 4, "Lect.May": 5,
            "Lect.Jun": 6, "Lect.Jul": 7, "Lect.Ago": 8, "Lect.Sep": 9, "Lect.Oct": 10,
            "Lect.Nov": 11, "Lect.Dic": 12,
        }

        consumo_map = {
            "M3 Ene": 1, "M3 Feb": 2, "M3 Mar": 3, "M3 Abr": 4, "M3 May": 5,
            "M3 Jun": 6, "M3 Jul": 7, "M3 Ago": 8, "M3 Sep": 9, "M3 Oct": 10,
            "M3 Nov": 11, "M3 Dic": 12,
        }

        pago_map = {
            "Pag.Ene": 1, "Pag.Feb": 2, "Pag.Mar": 3, "Pag.Abr": 4, "Pag.May": 5,
            "Pag.Jun": 6, "Pag.Jul": 7, "Pag.Ago": 8, "Pag.Set": 9, "Pag.Oct": 10,
            "Pag.Nov": 11, "Pag.Dic": 12,
        }

        deuda_map = {
            "Enero": 1, "Febrero": 2, "Marzo": 3, "Abril": 4,
            "Mayo": 5, "Junio": 6, "Julio": 7, "Agosto": 8,
            "Setiembre": 9, "Octubre": 10, "Noviembre": 11, "Diciembre": 12,
        }

        file = request.FILES.get('file')

        if not file:
            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(
                file,
                engine='openpyxl',
                # header=2,
                dtype={'Codigo': str}
            )
        except Exception as e:
            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        registros_creados = 0
        
        registros = []
        debts = []
        for index, row in df.iterrows():
        
            codigo = str(row.get('Codigo')).strip()
            customer = Customer.objects.get(codigo=codigo)
      
            tariff = customer.category
     
            for lect_col, month in month_map.items():

                consumo_col = [c for c, m in consumo_map.items() if m == month][0]
                deuda_col = [c for c, m in deuda_map.items() if m == month][0]
                pago_col = [c for c, m in pago_map.items() if m == month][0]

                current_reading = to_decimal_or_none(row.get(lect_col))
                consumption = to_decimal_or_none(row.get(consumo_col))
                deuda = to_decimal_or_none(row.get(deuda_col))
                print(deuda)
                pago = to_decimal_or_none(row.get(pago_col))

                # Si en este mes no hay lectura, consumo, deuda ni pago → cortamos
                if not any([current_reading, consumption, deuda, pago]):
                   break

                if consumption is not None:
                    previous_reading = current_reading - consumption
                else:
                    previous_reading = Decimal("0.00")

                if pago and pago > 0:

                    total_water = pago
                    paid = True

                elif deuda and deuda > 0:

                    total_water = deuda
                    paid = False

                else:

                    total_water = Decimal("0.00")
                    paid = False

                period_date = date(2026, month, 1)

                total_fixed_charge = tariff.price_fixed_charge
                total_sewer = tariff.price_sewer

                subtotal = total_water + tariff.price_sewer
                total_igv = calcular_igv_simple(subtotal)
                total_clean = tariff.price_clean

                sub_total_amount = (
            
                    total_water +
                    total_sewer +
                    total_igv
                )

                total_amount = (

                    sub_total_amount +
                    total_clean +
                    total_fixed_charge
                )

                registros.append(
                    Reading(
                        customer = customer,
                        period = date(2026, month, 1),
                        current_reading = current_reading or Decimal("0.00"),
                        previous_reading = previous_reading or Decimal("0.00"),
                        consumption = consumption or Decimal("0.00"),
                        total_water = total_water,
                        total_sewer = total_sewer,
                        total_clean = total_clean,
                        total_fixed_charge = total_fixed_charge,
                        total_igv = total_igv,
                        sub_total_amount = sub_total_amount,
                        total_amount = total_amount,
                        paid = paid
                    )
                )

        # Inserción masiva ignorando duplicados
        with transaction.atomic():
            
            # Guardar primero los readings
            Reading.objects.bulk_create(registros, ignore_conflicts=True)
    
            readings = Reading.objects.all()

            # 3. Preparar debts
            debts = []
            debt_details = []

            conceptos = {
                "001": CashConcept.objects.get(code="001"),
                "002": CashConcept.objects.get(code="002"),
                # "003": CashConcept.objects.get(code="003"),
                # "004": CashConcept.objects.get(code="004"),
                # "005": CashConcept.objects.get(code="005"),
            }

            for reading in readings:
                normalized_period = date(reading.period.year, reading.period.month, 1)

                debt = Debt(
                    customer=reading.customer,
                    period=normalized_period,
                    description="Deuda por consumo de agua/desagüe",
                    amount=reading.total_amount,
                    reading=reading
                )
                debts.append(debt)

            # 4. Insertar los debts en lote
            Debt.objects.bulk_create(debts, ignore_conflicts=True)

            # 5. Recuperar debts creados
            debts = Debt.objects.filter(reading__in=readings)

            # 6. Generar DebtDetails en lote
            for debt in debts:
                    
                    r = debt.reading
                    
                    if r.total_water > 0:
                        debt_details.append(
                            DebtDetail(debt=debt, concept=conceptos["001"], amount=r.total_water)
                        )
                    if r.total_sewer > 0:
                        debt_details.append(
                            DebtDetail(debt=debt, concept=conceptos["002"], amount=r.total_sewer)
                        )
                    # if r.total_fixed_charge > 0:
                    #     debt_details.append(
                    #         DebtDetail(debt=debt, concept=conceptos["003"], amount=r.total_fixed_charge)
                    #     )

                    # if r.total_clean > 0:
                    #     debt_details.append(
                    #         DebtDetail(debt=debt, concept=conceptos["004"], amount=r.total_clean)
                    #     )
                
                    # if r.total_igv > 0:
                    #     debt_details.append(
                    #         DebtDetail(debt=debt, concept=conceptos["005"], amount=r.total_igv)
                    #     )

            DebtDetail.objects.bulk_create(debt_details, ignore_conflicts=True)

        return Response({"message": "Lecturas importadas correctamente"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'])
    def receipt(self, request, pk=None, **kwargs):
        """
        Generar PDF de un solo recibo (para pruebas o impresion individual)
        """ 
   
        reading = Reading.objects.filter(customer_id=pk).order_by('-period').first()
        debt = Debt.objects.filter(customer_id=pk).order_by('-period').first()
        if not reading:

            return Response({"error": "No hay lecturas registradas"}, status=404)
        
        company = Company.objects.first()


        # Ruta al logo según el RUC
        logo_path = None
        if company and company.ruc:
            logo_path = request.build_absolute_uri(f"/media/{company.ruc}.jpeg")


        # obtener deudas anteriores no pagadas
        previous_debts = Debt.objects.filter(
            customer=reading.customer,
            paid=False,
            period__lt=reading.period
        ).order_by("period")

        # Agrupar por año
        yearly_data = defaultdict(lambda: {"total": 0, "months": []})
        for d in previous_debts:
            year = d.period.year
            month = d.period.month
            yearly_data[year]["total"] += float(d.amount)
            yearly_data[year]["months"].append(month)

        grouped_debts = []
        for year, data in yearly_data.items():
            min_month = min(data["months"])
            max_month = max(data["months"])
            grouped_debts.append({
                "year": year,
                "total": f"{data['total']:.2f}",
                "from_month": format_date(date(year, min_month, 1), "MMMM", locale="es").capitalize(),
                "to_month": format_date(date(year, max_month, 1), "MMMM", locale="es").capitalize(),
            })

        grouped_debts.sort(key=lambda x: x["year"], reverse=True)

        total_previous_debt = previous_debts.aggregate(total=Sum("amount"))["total"] or 0
        total_general = reading.total_amount + total_previous_debt

        # 🚀 armamos la misma estructura que en el masivo
        readings_context = [{
            "debt" : debt,
            "reading": reading,
            "grouped_debts": grouped_debts,
            "total_previous_debt": total_previous_debt,
            "total_general": total_general,
        }]

        print(readings_context)

        html = render_to_string("agua/recibo.html", {
            "readings_context": readings_context,
            "company": company,
            "company_logo": logo_path
        })

        pdf_bytes = HTML(string=html, base_url=request.build_absolute_uri('/')).write_pdf()

        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename=recibo_{reading.customer.codigo}_{reading.period.strftime("%Y-%m")}.pdf"'
        return response

# Límite seguro de recibos por PDF
MAX_RECIBOS_POR_PDF = 100

def chunked_queryset(iterable, size):
    """
    Divide una lista en bloques de tamaño fijo
    """
    for i in range(0, len(iterable), size):
        yield iterable[i:i + size]

class ReadingGenerationViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = ReadingGeneration.objects.all()
    serializer_class = ReadingGenerationSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """
        Genera lecturas y deudas automáticas para clientes sin medidor
        en el periodo indicado.
        """
        period_str = request.data.get("period")
        if not period_str:
            return Response({"error": "Falta el periodo (YYYY-MM)"}, status=400)

        try:
            period_date = datetime.strptime(period_str + "-01", "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Formato inválido de periodo"}, status=400)

        # Validar si ya existe una generación para ese periodo
        if ReadingGeneration.objects.filter(period=period_date).exists():
            return Response({"error": f"Ya se generaron lecturas para {period_str}."}, status=400)

        config = Config.objects.first()
        customers = Customer.objects.filter(has_meter=False)
        created = 0
        skipped_existing = 0
        skipped_paid = 0

        for customer in customers:
            # Verificar si ya tiene una lectura para ese periodo
            existing_reading = Reading.objects.filter(customer=customer, period=period_date).first()
            if existing_reading:
                skipped_existing += 1
                continue

            # Verificar si ya tiene una deuda pagada de ese periodo
            if Debt.objects.filter(customer=customer, period=period_date, paid=True).exists():
                skipped_paid += 1
                continue

            tariff = customer.category

            if config.add_igv_category:
              total_igv = calcular_igv_simple(tariff.price_water + tariff.price_sewer)
            else:
              total_igv = Decimal('0.00')

            sub_total_amount = tariff.price_water + tariff.price_sewer + total_igv

            # Crear lectura
            Reading.objects.create(
                customer=customer,
                period=period_date,
                previous_reading=0,
                current_reading=0,
                consumption=0,
                total_water=tariff.price_water,
                total_sewer=tariff.price_sewer,
                total_fixed_charge=tariff.price_fixed_charge,
                total_clean=tariff.price_clean,
                total_igv=total_igv,
                sub_total_amount=sub_total_amount,
                total_amount=sub_total_amount + tariff.price_fixed_charge + tariff.price_clean,
                paid=False,
                date_of_issue=request.data.get("date_of_issue"),
                date_of_due=request.data.get("date_of_due"),
                date_of_cute=request.data.get("date_of_cute")
            )

            created += 1

        # Registrar la generación
        generation = ReadingGeneration.objects.create(
            period=period_date,
            created_by=None,
            total_generated=created,
            notes=request.data.get("notes") or "Generación automática para clientes sin medidor",
            date_of_issue=request.data.get("date_of_issue"),
            date_of_due=request.data.get("date_of_due"),
            date_of_cute=request.data.get("date_of_cute")
        )

        return Response({
            "message": f"Generación completada para {period_str}.",
            "total_creados": created,
            "omitidos_existentes": skipped_existing,
            "omitidos_pagados": skipped_paid
        }, status=201)
    
    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        period = instance.period

        # Filtrar lecturas eliminables
        readings_to_delete = Reading.objects.filter(
            period=period,
            customer__has_meter=False,
            paid=False
        )

        deleted_count = readings_to_delete.count()

        # Eliminar deudas vinculadas a esas lecturas
        debts_to_delete = Debt.objects.filter(
            period=period,
            reading__in=readings_to_delete
        )
        debts_to_delete.delete()

        # Eliminar lecturas
        readings_to_delete.delete()

        # Eliminar la generación
        instance.delete()

        return Response({
            "message": f"Generación del periodo {period.strftime('%Y-%m')} anulada correctamente.",
            "lecturas_eliminadas": deleted_count
        }, status=204)

    @action(detail=False, methods=['get'])
    def download_receipts_by_zone(self, request):

        """
        Descargar recibos dinámicamente por zona + periodo
        """

        company = Company.objects.first()

        zona_id = request.query_params.get("zona")
        month = request.query_params.get("month")

        if not zona_id:
            return Response({"error": "Debe enviar el parámetro zona"}, status=400)

        if not month:
            return Response({"error": "Debe enviar el parámetro month"}, status=400)

        # 🔹 convertir "2026-04" → date
        try:
            period = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            return Response({"error": "Formato de month inválido (YYYY-MM)"}, status=400)

        # 🔹 lecturas
        readings = (
            Reading.objects.filter(
                period__year=period.year,
                period__month=period.month,
                customer__zona_id=zona_id
            )
            .select_related("customer", "customer__zona")
            .prefetch_related(
                Prefetch(
                    "customer__debts",
                    queryset=Debt.objects.filter(
                        paid=False,
                        period__lt=period
                    ),
                    to_attr="previous_debts"
                )
            )
            .order_by("customer__codigo")
        )

        if not readings.exists():
            return Response(
                {"error": "No hay recibos para esta zona"},
                status=400
            )

        readings_list = list(readings)
        zona = readings_list[0].customer.zona

        buffer = io.BytesIO()
        zip_filename = f"recibos_zona_{zona.name}_{month}.zip"

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:

            for idx, chunk in enumerate(
                chunked_queryset(readings_list, MAX_RECIBOS_POR_PDF),
                start=1
            ):
                all_readings_context = []

                for reading in chunk:
                    previous_debts = reading.customer.previous_debts

                    yearly_data = defaultdict(
                        lambda: {"total": Decimal("0.00"), "months": []}
                    )

                    for d in previous_debts:
                        year = d.period.year
                        month_d = d.period.month
                        yearly_data[year]["total"] += d.amount
                        yearly_data[year]["months"].append(month_d)

                    grouped_debts = []
                    for year, data in yearly_data.items():
                        grouped_debts.append({
                            "year": year,
                            "total": f"{data['total']:.2f}",
                            "from_month": format_date(
                                date(year, min(data["months"]), 1),
                                "MMMM",
                                locale="es"
                            ).capitalize(),
                            "to_month": format_date(
                                date(year, max(data["months"]), 1),
                                "MMMM",
                                locale="es"
                            ).capitalize(),
                        })

                    grouped_debts.sort(key=lambda x: x["year"], reverse=True)

                    total_previous_debt = sum(
                        (d.amount for d in previous_debts),
                        Decimal("0.00")
                    )

                    total_general = reading.total_amount + total_previous_debt

                    all_readings_context.append({
                        "reading": reading,
                        "grouped_debts": grouped_debts,
                        "total_previous_debt": total_previous_debt,
                        "total_general": total_general,
                    })

                html_content = render_to_string(
                    "agua/recibo.html",
                    {
                        "readings_context": all_readings_context,
                        "company": company,
                        "zona": zona.name,
                    }
                )

                pdf_bytes = HTML(
                    string=html_content,
                    base_url=request.build_absolute_uri('/')
                ).write_pdf()

                zip_file.writestr(
                    f"{zona.name}_parte_{idx}.pdf",
                    pdf_bytes
                )

        buffer.seek(0)
        response = HttpResponse(buffer, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{zip_filename}"'
        return response

    @action(detail=False, methods=['get'])
    def download_all_receipts(self, request):
        """
        Descargar un único PDF con todos los recibos de este periodo
        dentro de un ZIP
        """
        company = Company.objects.first()

        month = request.query_params.get("month")
        calle_id = request.query_params.get("calle")

        if not month:
            return Response({"error": "Debe enviar el parámetro month"}, status=400)

        # 🔹 convertir "2026-04" → date
        try:
            period = datetime.strptime(month, "%Y-%m").date()
        except ValueError:
            return Response({"error": "Formato de month inválido (YYYY-MM)"}, status=400)

        # 🔹 base queryset
        readings = Reading.objects.filter(
            period__year=period.year,
            period__month=period.month
        ).select_related("customer", "customer__calle")

        # 🔹 filtro por calle (opcional)
        calle = None
        if calle_id:
            calle = Calle.objects.get(pk=calle_id)
            readings = readings.filter(customer__calle_id=calle_id)


        if not readings.exists():
            return Response(
                {"error": "No hay lecturas con calle asignada para este periodo"},
                status=400
            )

        all_readings_context = []
        for reading in readings:

            # obtener deudas anteriores no pagadas
            previous_debts = Debt.objects.filter(
                customer=reading.customer,
                paid=False,
                period__lt=reading.period
            ).order_by("period")

            # Agrupar por año
            yearly_data = defaultdict(lambda: {"total": 0, "months": []})
            for d in previous_debts:
                year = d.period.year
                month = d.period.month
                yearly_data[year]["total"] += float(d.amount)
                yearly_data[year]["months"].append(month)

            grouped_debts = []
            for year, data in yearly_data.items():
                min_month = min(data["months"])
                max_month = max(data["months"])
                grouped_debts.append({
                    "year": year,
                    "total": f"{data['total']:.2f}",
                    "from_month": format_date(date(year, min_month, 1), "MMMM", locale="es").capitalize(),
                    "to_month": format_date(date(year, max_month, 1), "MMMM", locale="es").capitalize(),
                })

            grouped_debts.sort(key=lambda x: x["year"], reverse=True)

            total_previous_debt = previous_debts.aggregate(total=Sum("amount"))["total"] or 0
            total_general = reading.total_amount + total_previous_debt

            all_readings_context.append({
                "reading": reading,
                "grouped_debts": grouped_debts,
                "total_previous_debt": total_previous_debt,
                "total_general": total_general,
            })

        # Renderizamos todos los recibos (un reading por página)
        html_content = render_to_string("agua/recibo.html", {
            "readings_context": all_readings_context,
            "company": company,
        })

        pdf_bytes = HTML(string=html_content, base_url=request.build_absolute_uri('/')).write_pdf()
        filename = f"recibos_{month}"
        if calle:
           filename = f"{calle.name}_{month}"
        # Devolvemos directamente el PDF
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="{filename}.pdf"'
        )

        return response
 
class DebtViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Debt.objects.all().order_by('period')
    serializer_class = DebtSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_class = DebtFilter

    @transaction.atomic
    def create(self, request, *args, **kwargs):

        config = Config.objects.first()
        data = request.data
        customer_id = data.get("customer")
        period_str = data.get("period")

        if not customer_id or not period_str:
            raise ValidationError("Debe enviar 'customer' y 'period'.")

        period = date.fromisoformat(period_str)
        normalized_period = date(period.year, period.month, 1)

        # Obtener cliente
        try:
            customer = Customer.objects.get(id=customer_id)
        except Customer.DoesNotExist:
            raise ValidationError("El cliente no existe.")

        # ⚠️ Evitar duplicados
        if Debt.objects.filter(customer=customer, period=normalized_period).exists():
            raise ValidationError("Ya existe una deuda para este cliente y periodo.")

    
        # Calcular montos base
        total_fixed_charge = customer.category.price_fixed_charge
        total_water = customer.category.price_water
        total_sewer = customer.category.price_sewer
        total_clean = customer.category.price_clean
        
        if config.add_igv_category:
           total_igv = calcular_igv_simple(total_water + total_sewer)
        else:
           total_igv = Decimal('0.00')

        sub_total_amount = total_water + total_sewer + total_igv
        total_amount = sub_total_amount + total_fixed_charge + total_clean

        # Crear lectura asociada (sin procesos automáticos)
        reading = Reading(
            customer=customer,
            period=normalized_period,
            current_reading=Decimal("0.000"),
            has_meter=customer.has_meter,
            total_water=total_water,
            total_sewer=total_sewer,
            total_fixed_charge=total_fixed_charge,
            total_clean=total_clean,
            total_igv=total_igv,
            sub_total_amount=sub_total_amount,
            total_amount=total_amount,
        )
        reading.save(skip_process=True)

        # ✅ Crear deuda vinculada
        debt = Debt.objects.create(
            customer=customer,
            period=normalized_period,
            amount=total_amount,
            description=f"Deuda del periodo {period.strftime('%Y-%m')}",
            reading=reading,  # 👈 vinculación directa
        )

        concept_map = {
            "price_water": total_water,
            "price_sewer": total_sewer,
            "price_fixed_charge": total_fixed_charge,
            "price_clean": total_clean,
            "price_igv": total_igv,
        }

        concepts = CashConcept.objects.filter(
            system_key__in=concept_map.keys()
        )

        concept_dict = {c.system_key: c for c in concepts}

        for key, amount in concept_map.items():

            if amount > 0 and key in concept_dict:

                DebtDetail.objects.create(
                    debt=debt,
                    concept=concept_dict[key],
                    amount=amount
                )

        # Respuesta
        serializer = self.get_serializer(debt)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):

        instance = self.get_object()
        data = request.data

        details_data = data.get("details", [])

        sent_ids = [d.get("id") for d in details_data if d.get("id")]

        # eliminar los detalles que ya no vienen
        for detail in instance.details.all():

            if detail.id not in sent_ids:
                detail.delete()

        for d in details_data:

            detail_id = d.get("id")
            concept_id = d.get("concept_id")
            amount = d.get("amount")
            
            detail = DebtDetail.objects.get(id=detail_id, debt=instance)
            detail.concept_id = concept_id or detail.concept_id
            detail.amount = amount
            detail.save()

        # recalcular total
        total = sum(detail.amount for detail in instance.details.all())
      
        instance.amount = total
        instance.save()

        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def import_excel(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            df = pd.read_excel(
                file,
                engine='openpyxl',
                # header=2,
                dtype={'Codigo': str}
            )

            df['Codigo'] = df['Codigo'].astype(str).str.strip().str[-5:].str.zfill(5)
        except Exception as e:
            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        errores = []
        procesados = 0

        # 🔹 Precargar conceptos
        conceptos = {
            "001": CashConcept.objects.get(code="001"),
            "002": CashConcept.objects.get(code="002"),
            # "003": CashConcept.objects.get(code="003"),
            # "004": CashConcept.objects.get(code="004"),
            # "005": CashConcept.objects.get(code="005"),
        }

        # 🔹 Precargar clientes del Excel
        codigos_excel = df['Codigo'].unique()
        clientes = {
            c.codigo: c
            for c in Customer.objects.filter(codigo__in=codigos_excel)
        }

        debts_to_create = []
        details_to_create = []

        try:

            cargo_fijo = CashConcept.objects.get(code="003")

        except CashConcept.DoesNotExist:

            cargo_fijo = None

        total_fixed_charge = cargo_fijo.total if cargo_fijo else Decimal("0.00")
        # df = df.head(2)

        for row in df.itertuples(index=False):

            codigo = str(row.Codigo)

  

            year = row.anio
            meses_texto = to_none_if_empty(row.Meses)
            total = to_decimal_or_none(row.Agua)

            if year != 2026:
                if not meses_texto:
                    errores.append({"codigo": codigo, "anio": year, "total": total, "error": "Campo 'Meses' vacio"})
                    continue

                customer = clientes.get(codigo)
                if not customer:
                    errores.append({"codigo": codigo, "anio": year, "meses": meses_texto, "total": total, "error": "Cliente no encontrado"})
                    continue

                try:
                    periodos = generar_periodos(int(year), meses_texto)
                except Exception as e:
                    errores.append({"codigo": codigo, "anio": year, "meses": meses_texto, "total": total, "error": f"Error al generar periodos: {str(e)}"})
                    continue

                # Calcular montos con precisión decimal
                total_water = (Decimal(total) / Decimal(len(periodos))) if (total and len(periodos) > 0) else Decimal("0.00")
                total_sewer = Decimal(customer.category.price_sewer or 0)
                total_fixed_charge = Decimal(customer.category.price_fixed_charge or 0)

                amount = total_water + total_sewer + total_fixed_charge
                if amount <= Decimal("0.00"):
                    print(f"Deuda ignorada para {codigo} monto 0")
                    continue
                for periodo in periodos:
                    # 🔹 Obtener o crear debt en memoria, no en DB aún

                    reading = Reading(
                        customer=customer,
                        period=periodo,
                        current_reading=Decimal("0.000"),
                        has_meter=customer.has_meter,
                        total_water=total_water,
                        total_sewer=total_sewer,
                        total_fixed_charge=total_fixed_charge,
                        total_amount=amount,
                    )
                    reading.save(skip_process=True)

                    debt, created = Debt.objects.get_or_create(
                        customer=customer,
                        reading=reading,
                        period=periodo,
                        defaults={
                            "description": "Deuda importada desde Excel",
                            "amount": amount,
                            "paid": False
                        }
                    )

                    if not created:
                        debt.amount = amount
                        debt.save()
                        debt.details.all().delete()

                    # 🔹 Preparar detalles para bulk_create
                    if total_water > 0:
                        details_to_create.append(DebtDetail(debt=debt, concept=conceptos["001"], amount=total_water))
                    if total_sewer > 0:
                        details_to_create.append(DebtDetail(debt=debt, concept=conceptos["002"], amount=total_sewer))
                    # if total_fixed_charge > 0:
                    #     details_to_create.append(DebtDetail(debt=debt, concept=conceptos["003"], amount=total_fixed_charge))

                    procesados += 1

        # 🔹 Insertar todos los detalles de una vez
        if details_to_create:
            DebtDetail.objects.bulk_create(details_to_create)

        return Response({
            "procesados": procesados,
            "errores": errores
        }, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def create_reading(self, request, pk=None):
        debt = self.get_object()

        if debt.reading:

            return Response(
                {"detail": "Esta deuda ya tiene una lectura vinculada."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Crear lectura SIN procesar
        reading = Reading(
            customer=debt.customer,
            paid=debt.paid,
            period=debt.period,
            current_reading=Decimal("0.000"),
            has_meter=debt.customer.has_meter,
        )

        reading.save(skip_process=True)  # 👈 aquí usamos el flag

        # Vincular lectura con deuda existente
        debt.reading = reading
        debt.save(update_fields=["reading"])

        return Response(
            {"detail": f"Lectura creada y vinculada correctamente a la deuda {debt.id}."},
            status=status.HTTP_201_CREATED
        )

    @action(detail=False, methods=['post'])
    def refinanciar(self, request):

        tenant = connection.schema_name

        if tenant != "chilca":
            raise ValidationError("Refinanciación no disponible")

        customer_id = request.data.get("customer_id")
        years = request.data.get("years", [])
        cuotas = int(request.data.get("cuotas", 1))

        if not years:
            raise ValidationError("Debe seleccionar al menos un año")

        if cuotas <= 0:
            raise ValidationError("Cuotas inválidas")

        debts = Debt.objects.filter(
            customer_id=customer_id,
            paid=False,
            is_refinanced=False,
            period__year__in=years   # 🔥 CLAVE
        )

        if not debts.exists():
            raise ValidationError("No hay deudas válidas")

        total = debts.aggregate(total=Sum('amount'))['total'] or 0

        with transaction.atomic():

            ref = DebtRefinancing.objects.create(
                customer_id=customer_id,
                total_amount=total
            )

            # vincular deudas
            for d in debts:
                DebtRefinancingDetail.objects.create(
                    refinancing=ref,
                    debt=d
                )
                d.is_refinanced = True
                d.save()

            # generar cuotas
            monto_cuota = total / cuotas

            for i in range(1, cuotas + 1):
                RefinancingInstallment.objects.create(
                    refinancing=ref,
                    number=i,
                    amount=monto_cuota
                )

        return Response({
            "message": "Refinanciación creada",
            "total": total,
            "cuotas": cuotas
        })

    @action(detail=False, methods=['post'])
    def preview_refinanciamiento(self, request):

        customer_id = request.data.get("customer_id")
        years = request.data.get("years", [])
        cuotas = int(request.data.get("cuotas", 1))

        debts = Debt.objects.filter(
            customer_id=customer_id,
            paid=False,
            is_refinanced=False,
            period__year__in=years
        )

        total = debts.aggregate(total=Sum('amount'))['total'] or 0

        monto_cuota = round(total / cuotas, 2)

        cuotas_preview = []

        for i in range(1, cuotas + 1):
            cuotas_preview.append({
                "numero": i,
                "monto": monto_cuota
            })

        return Response({
            "total": total,
            "cuotas": cuotas_preview
        })

class RefinancingInstallmentViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = RefinancingInstallment.objects.all()
    serializer_class = RefinancingInstallmentSerializer
  
    def get_queryset(self):

        queryset = super().get_queryset()

        customer_id = self.request.query_params.get('customer')
        paid = self.request.query_params.get('paid')

        if customer_id:
            queryset = queryset.filter(
                refinancing__customer_id=customer_id  # 🔥 clave
            )

        if paid is not None:
            queryset = queryset.filter(paid=(paid == 'true'))

        return queryset.order_by('number')

class InvoiceViewSet(TenantSafeMixin, viewsets.ModelViewSet):

    queryset = Invoice.objects.all().order_by('-id')
    serializer_class = InvoiceSerializer
    pagination_class = CustomPagination
    filter_backends = [DjangoFilterBackend,filters.SearchFilter]
    search_fields = ['customer__codigo', 'customer__full_name', 'customer__number']

    permission_classes = [TenantPaymentCreatePermission]

    @action(detail=True, methods=['get'], url_path='ticket')
    def ticket_pdf(self, request, pk=None, **kwargs):

        invoice = get_object_or_404(Invoice, id=pk)

        # Usamos la relación inversa para evitar consultas innecesarias
        payments_debts = invoice.invoice_debts.select_related('debt').order_by('debt__period')
        payments_concepts = invoice.invoice_concepts.select_related('concept').order_by('concept__code')
        payments_installments = invoice.invoice_installments.select_related('installment__refinancing').order_by('installment__number')

        company = Company.objects.first()


        # Ruta al logo según el RUC
        logo_path = None
        if company and company.ruc:
            logo_path = request.build_absolute_uri(f"/media/{company.ruc}.jpeg")

        context = {
            "invoice": invoice,
            "customer": invoice.customer,
            "concepts": payments_concepts,
            "payments": payments_debts,
            "installments": payments_installments,  # 👈 NUEVO
            "total_paid": sum((p.total for p in payments_debts), 0),
            "total_paid_concept": sum((p.total for p in payments_concepts), 0),
            # "total_paid_installments": sum((p.total for p in payments_installments), 0),  # 👈 opcional
            "company_name": company.name if company else "",
            "company_ruc": company.ruc if company else "",
            "company_logo": logo_path,
        }
        
        template = get_template('agua/invoice.html')
        html_string = template.render(context)

        pdf_buffer = io.BytesIO()
   
        HTML(string=html_string, base_url=request.build_absolute_uri()).write_pdf(
            pdf_buffer
        )

        file_name = f"ticket_{invoice.id}.pdf"
        pdf_buffer.seek(0)
        response = HttpResponse(pdf_buffer.read(), content_type="application/pdf")
        response["Content-Disposition"] = f'inline; filename="{file_name}"'
        return response

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        invoice = self.get_object()
        invoice.cancel()
        return Response({"message": "Factura anulada"}, status=status.HTTP_200_OK)

class CashConceptViewSet(TenantSafeMixin, viewsets.ModelViewSet):

    queryset = CashConcept.objects.all().order_by('id')
    serializer_class = CashConceptSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter
    ]

    search_fields = ['name']

    filterset_fields = ['is_master', 'is_master_view', 'state']

class CategoryViewSet(TenantSafeMixin,viewsets.ModelViewSet):
    
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    queryset = Category.objects.all() 

    def get_queryset(self):

        return Category.objects.filter(state=True).order_by('id')

    @action(detail=False, methods=['post'])
    def import_excel(self, request):

        file = request.FILES.get('file')

        if not file:

            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:

            extension = os.path.splitext(file.name)[1].lower()

            if extension == ".xls":

                df = pd.read_excel(file, engine="xlrd", dtype={'codigo': str})

            elif extension == ".xlsx":

                df = pd.read_excel(file, engine="openpyxl", dtype={'codigo': str})

            else:

                return Response({'error': 'Formato no soportado. Solo .xls o .xlsx'}, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:

            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        for index, row in df.sort_values(by='codigo').iterrows():

            codigo = str(row.get('codigo')).zfill(2)  # Siempre 2 dígitos
            descrip = row.get('descrip')
            agua = row.get('agua')

            # Crear o actualizar registro
            Category.objects.update_or_create(
                codigo=codigo,
                defaults={
                    'name': descrip,
                    'price_water': agua,
                    'price_sewer': 0,
                    'has_meter': False  
                }
            )

            print(f"Importado: {codigo} - {descrip} - {agua}")


        return Response({"message":"ubicacion cargada"}, status=status.HTTP_200_OK)

class ViaViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Via.objects.all().order_by('id')
    serializer_class = ViaSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name']
    ordering_fields = ['name']

    @action(detail=False, methods=['post'])
    def import_excel(self, request):

        file = request.FILES.get('file')

        if not file:

            return Response({'error': 'No se proporciono un archivo.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
        
            df = pd.read_excel(
                    file,
                    engine='openpyxl',
                    dtype={
                        'tipo_dir': str,
                        'codigo': str
                    })

        except Exception as e:

            return Response({'error': f'Error al leer el archivo: {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

        # for index, row in df.sort_values(by='tipo_dir').iterrows():

        #     name = row.get('abrv')
        #     codigo = str(row.get('tipo_dir')).zfill(2)  # Siempre 2 dígitos

        #     if Via.objects.filter(codigo=codigo).exists():
        #         continue

        #     via = Via(name=name, codigo=codigo)
        #     via.save()

        df = df.sort_values(by=['codigo'], ascending=True)
        for index, row in df.iterrows():

            codigo = str(row.get('codigo') or '').strip()
            name = str(row.get('nombre') or '').strip()
            codigo_via = int(row.get('tipo_dir'))

            print(codigo, name, codigo_via)

            if not name or not codigo_via:
                
               print(f'Fila {index + 2}: calle invalida (nombre o id_via vacio)')
               continue

            try:

                via = Via.objects.get(pk=codigo_via)

            except Via.DoesNotExist:

                print(f'Fila {index + 2}: via con codigo {codigo_via} no existe (para la calle "{name}")')

                continue

            # if Calle.objects.filter(name=name, via=via).exists():

            #     print(f'Fila {index + 2}: ya existe la calle "{name}" en la via {via.name}')
            #     continue

            calle = Calle(name=name, via=via, codigo=codigo)
            calle.save()

        return Response({"message":"ubicacion cargada"}, status=status.HTTP_200_OK)

class CalleViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Calle.objects.select_related('via').all().order_by('id')
    serializer_class = CalleSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['via']  # permite filtrar por tipo_via id
    search_fields = ['codigo','name']

class ZonaViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Zona.objects.all().order_by('id')
    serializer_class = ZonaSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['codigo','name']

class CompanyViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = Company.objects.all()
    serializer_class = CompanySerializer

class CashOutflowViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    queryset = CashOutflow.objects.all().order_by('-id')
    serializer_class = CashOutflowSerializer
    pagination_class = CustomPagination

class ConfigViewSet(TenantSafeMixin,viewsets.ModelViewSet):

    authentication_classes = []
    permission_classes = []

    queryset = Config.objects.all().order_by('-id')
    serializer_class = ConfigSerializer
    pagination_class = CustomPagination

class BaseMorosidadListView(ListAPIView):

    serializer_class = MorosidadSerializer

    def get_queryset(self):
        # Clientes que tienen al menos UNA deuda impaga
        return (
            Customer.objects
            .filter(debts__paid=False)
            .distinct()
        )
    
class MorosidadOnTimeView(BaseMorosidadListView):

    pagination_class = CustomPagination
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                unpaid_months=Count('debts__id', filter=Q(debts__paid=False), distinct=True)
            )
            .filter(unpaid_months__lte=2)
            .order_by('codigo')
        )

class MorosidadOverdueView(BaseMorosidadListView):

    pagination_class = CustomPagination
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(
                unpaid_months=Count('debts__id', filter=Q(debts__paid=False), distinct=True)
            )
            .filter(unpaid_months__gt=2)
            .order_by('codigo')
        )

class DashboardSummaryAPIView(TenantSafeMixin, APIView):

    def get(self, request):

        today = date.today()
        month_start = today.replace(day=1)

        # 1️⃣ Clientes totales
        total_customers = Customer.objects.count()

        # 2️⃣ Clientes con deuda
        customers_with_debt = (
            Debt.objects
            .filter(paid=False)
            .values('customer')
            .distinct()
            .count()
        )

        # 3️⃣ Recaudación del mes
        monthly_revenue = (
            InvoicePayment.objects
            .filter(created_at__date__gte=month_start)
            .aggregate(total=Sum('total'))['total'] or 0
        )

        # 4️⃣ Recaudación del día
        daily_revenue = (
            InvoicePayment.objects
            .filter(created_at__date=today)
            .aggregate(total=Sum('total'))['total'] or 0
        )

        # 5️⃣ Top 5 clientes con más deuda
        top_debtors = (
            Debt.objects
            .filter(paid=False)
            .values(
                'customer__id',
                'customer__full_name'
            )
            .annotate(total_debt=Sum('amount'))
            .order_by('-total_debt')[:5]
        )

        weekly_income = []

        for i in range(4, 0, -1):
            start_week = today - timedelta(days=i * 7)
            end_week = start_week + timedelta(days=6)

            total = (
                InvoicePayment.objects
                .filter(
                    created_at__date__gte=start_week,
                    created_at__date__lte=end_week
                )
                .aggregate(total=Sum('total'))['total'] or 0
            )

            weekly_income.append({
                "label": f"Semana {5 - i}",
                "total": float(total)
            })

        # 6️⃣ Deuda por zona
        debt_by_zone = (
            Debt.objects
            .filter(paid=False, customer__zona__isnull=False)
            .values(
                'customer__zona__id',
                'customer__zona__name'
            )
            .annotate(total_debt=Sum('amount'))
            .order_by('-total_debt')
        )

        # Total deuda pendiente
        total_debt = (
            Debt.objects
            .filter(paid=False)
            .aggregate(total=Sum('amount'))['total'] or 0
        )

        # Total recaudado (histórico)
        total_collected = (
            Invoice.objects
            .aggregate(total=Sum('total'))['total'] or 0
        )


        return Response({
            "cards": [
                {
                    "title": "Clientes Totales",
                    "icono" : "fa-solid fa-users",
                    "value": total_customers,
                },
                {
                    "title": "Clientes con Deuda",
                    "icono" : "fa-solid fa-user-slash",
                    "value": customers_with_debt,
                },
                {
                    "title": "Recaudación del Mes",
                    "icono" : "fa-solid fa-chart-line",          
                    "value": f"S/ {monthly_revenue}",
                },
                {
                    "title": "Recaudación del Día",
                    "icono" : "fa-solid fa-calendar-day",  
                    "value": f"S/ {daily_revenue}",
                },
            ],

            "top_debtors": top_debtors,
            "weekly_income": weekly_income,
            "charts": {
                "weekly_income": weekly_income,
                "debt_by_zone": debt_by_zone
            },
            "financial_comparison": {
                "debt": float(total_debt),
                "collected": float(total_collected)
            },
        })

class ProcessPayment(TenantSafeMixin, APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

        payment_data = {
            "transaction_amount": float(request.data["transaction_amount"]),
            "installments": int(request.data["installments"]),  # normalmente 1
            "token": request.data["token"],
            "payment_method_id": request.data["payment_method_id"],
            "issuer_id": request.data.get("issuer_id"),
            "description": "Pago servicio de agua",
            "payer": {
                "email": request.data["payer"]["email"],
                "identification": request.data["payer"].get("identification")
            },
            "additional_info": {
                "items": [
                    {
                        "id": "SERV-AGUA",
                        "title": "Servicio de agua potable",
                        "category_id": "utilities",
                        "quantity": 1,
                        "unit_price": float(request.data["transaction_amount"])
                    }
                ]
            },
            "external_reference": request.data["external_reference"],
            "metadata": {
                "tenant": request.data["tenant_schema"],
                "customer_id": request.data["customer_id"],
                "debt_ids": request.data["debt_ids"],
            }

        }

        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]

        return Response(payment)
    
class ProcessPaymentYape(TenantSafeMixin, APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)
        token = request.data.get("token")
        amount = request.data.get("amount")

        request_options = mercadopago.config.RequestOptions()
        request_options.custom_headers = {
            "X-Idempotency-Key": str(uuid.uuid4())
        }

        payment_data = {
            "description": "Pago servicio agua",
            "payment_method_id": "yape",
            "token": token,
            "transaction_amount": float(amount),
            "installments": 1,
            "notification_url": settings.MP_WEBHOOK_URL,
            "external_reference": request.data["external_reference"],
            "metadata": {
                "tenant": request.data["tenant_schema"],
                "customer_id": request.data["customer_id"],
                "debt_ids": request.data["debt_ids"],
            },
            "payer": {
                "email": "pablo_joseph01@hotmail.com"
            },
        }

        payment_response = sdk.payment().create(
            payment_data,
            request_options
        )

        return Response(payment_response["response"])
    
class PaymentStatusView(TenantSafeMixin, APIView):
    
    authentication_classes = []
    permission_classes = []

    def get(self, request, payment_id):

        pay = Pay.objects.filter(payment_id=payment_id).first()

        if not pay:

            return Response({"status": "not_found"}, status=404)

        data = {
            "status": pay.status,
            "processed": pay.processed
        }

        if pay.processed:
        
            invoice = Invoice.objects.filter(payment_reference=pay.payment_id).first()

            if invoice:

                data.update({

                    "id": invoice.id,
                    "code" : invoice.code

                })

        return Response(data)