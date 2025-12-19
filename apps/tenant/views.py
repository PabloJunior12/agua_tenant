from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.contrib.auth import authenticate
from django_tenants.utils import schema_context, get_tenant_model
from .models import Client, GlobalBackup, TenantBackup
from .serializers import ClientSerializer, GlobalBackupSerializer, TenantBackupSerializer
from apps.user.models import User,UserPermission, Module
from django.db import connection, transaction
from apps.agua.models import Company
from .utils.seed import load_initial_data
from bs4 import BeautifulSoup
import csv
import io
import requests
from django.http import HttpResponse
from django.core.management import call_command
import os
from django.http import FileResponse, Http404
from rest_framework.views import APIView
import mercadopago
from django.conf import settings
import json

class ValidateTenantView(APIView):

    def get(self, request, schema_name):

        Tenant = get_tenant_model()

        exists = Tenant.objects.filter(schema_name=schema_name).exists()

        if exists:

            return Response({'valid': True}, status=status.HTTP_200_OK)
        
        return Response({'valid': False}, status=status.HTTP_404_NOT_FOUND)

class ClientViewSet(viewsets.ModelViewSet):

    queryset = Client.objects.all().order_by('id')
    serializer_class = ClientSerializer

    def create(self, request, *args, **kwargs):

        schema_name = request.data.get('schema_name')
        
        user_data = request.data.get('user')
        company_data = request.data.get('company')

        schema_name = schema_name.lower()
     
        if Client.objects.filter(schema_name=schema_name).exists():
            return Response({'error': 'Ya existe un tenant con ese nombre.'}, status=status.HTTP_400_BAD_REQUEST)

        client = Client.objects.create(
            schema_name=schema_name,
        )

        # 2️⃣ Crear usuario asociado al tenant
        password = user_data.pop('password', None)
        user = User(**user_data)
        user.tenant = client
        user.is_staff = False
        user.is_admin = True
        if password:
            user.set_password(password)
        user.save()

        modules = Module.objects.all()

        # Crear permisos asociados

        for module in modules:

            UserPermission.objects.create(user=user, module=module)

        load_initial_data(client.schema_name, user, company_data)

        serializer = self.get_serializer(client)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):

        client = self.get_object()
        schema_name = client.schema_name

        if schema_name == "public":
            return Response(
                {"error": "No se puede eliminar el tenant público."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 🧭 1️⃣ Cambiamos al schema del tenant
            connection.set_schema(schema_name)

            # 2️⃣ Eliminamos los usuarios que pertenecen a este tenant (aún dentro del schema)
            users = User.objects.filter(tenant=client)
            user_count = users.count()
            users.delete()

        except Exception as e:
            return Response(
                {"error": f"Error eliminando usuarios del tenant: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        finally:
            # 3️⃣ Cerramos conexión para evitar errores de schema inexistente
            connection.close()

            # 4️⃣ Eliminamos el schema manualmente
            with connection.cursor() as cursor:
                cursor.execute(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE;')

            # 5️⃣ Eliminamos el registro de la compañía en public
            connection.set_schema_to_public()
            client.delete()

        return Response(
            {
                "message": f'Tenant "{schema_name}" eliminado correctamente junto con {user_count} usuario(s).'
            },
            status=status.HTTP_204_NO_CONTENT,
        )

    def update(self, request, *args, **kwargs):

        client = self.get_object()
        serializer = self.get_serializer(client, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

class ConecctMineco(APIView):

    session = requests.Session()  # Mantener la sesión activa

    def get(self, request):

        """Descarga el CAPTCHA y lo envía a Angular como base64"""
        captcha_url = "https://apps4.mineco.gob.pe/siafadmapp/jcaptcha.jpg"
        captcha_response = self.session.get(captcha_url)

        if captcha_response.status_code == 200:
            # Convertir imagen a base64 para enviarla a Angular
            import base64
            captcha_base64 = base64.b64encode(captcha_response.content).decode("utf-8")

            return Response({"captcha": captcha_base64})
        else:
            return Response({"error": "Error al descargar el captcha"}, status=400)

    def post(self, request):

        username = request.data.get("username")
        password = request.data.get("password")
        captcha_text = request.data.get("captcha")

        login_url = "https://apps4.mineco.gob.pe/siafadmapp/j_spring_security_check"
        payload = {
            "j_username": username,
            "j_password": password,
            "jcaptcha": captcha_text,
            "btnIngresar": "Ingresar"
        }

        headers = {
            "User-Agent": request.headers.get("User-Agent", ""),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "es-ES,es;q=0.6",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://apps4.mineco.gob.pe/siafadmapp/login",
            "Origin": "https://apps4.mineco.gob.pe",
            "Connection": "keep-alive",
        }

        login_response = self.session.post(login_url, data=payload, headers=headers, allow_redirects=True)
        jsessionid = self.session.cookies.get("JSESSIONID")
 

        if jsessionid:

            menu_url = "https://apps4.mineco.gob.pe/siafadmapp/privado/menu"

            header_menu = {
                "Cookie" : f"JSESSIONID={jsessionid};"
            } 

            menu_response = requests.get(menu_url, headers=header_menu)

            soup = BeautifulSoup(menu_response.text, 'html.parser')

            # Buscar la etiqueta <title>
            title_tag = soup.find("title")

            if title_tag and "Inicio de sesión" in title_tag.text:
                
                return Response({"error": "Error al iniciar sesion, Vuelve a intentarlo"}, status=status.HTTP_400_BAD_REQUEST)
                
            else:
     
                return Response({"JSESSIONID": jsessionid})
        else:

            return Response({"error": "Error al iniciar sesion, Vuelve a intentarlo"}, status=status.HTTP_400_BAD_REQUEST)

class ImportSiafApiView(APIView):
    def post(self, request):
        token = request.data.get('token')
        year = request.data.get('year')

        if not token or not year:
            return Response(
                {"error": "Parámetros 'token' y 'year' son requeridos."},
                status=status.HTTP_400_BAD_REQUEST
            )

        url = (
            f"https://apps4.mineco.gob.pe/siafadmapp/privado/registros/"
            f"pca/getListEntidadesPorAnio?anioEje={year}&restringirSecEjec=S"
        )
        headers = {"Cookie": f"JSESSIONID={token};"}

    
        response = requests.get(url, headers=headers, timeout=15)

        # Intentar decodificar JSON de forma segura

        try:
            
            data = response.json()

        except ValueError:

            # No era JSON válido (probablemente HTML o sesión expirada)

            return Response(
                {
                    "error": "La respuesta del servidor no es JSON válido.",
                    "html_fragmento": response.text[:300]
                },
                status=status.HTTP_502_BAD_GATEWAY
            )

        # Si todo está bien
        return Response(data)

class MetasView(APIView):

    def post(self, request):

        token = request.data.get('token')
        option = request.data.get('option')
        year = request.data.get('year')
        sec_ejec = request.data.get('secEjec')

        # DASHBOARD
 
        url = f"https://apps4.mineco.gob.pe/siafadmapp/privado/registros/metaPresupuestal/getListMetaPresupuestal?anoEje={year}&secEjec={sec_ejec}&categoria=&programa=&_search=false&nd=1753300853786&rows=10000&page=1&sidx=&sord=asc"

        headers = { "Cookie" : f"JSESSIONID={token};" }

        response = requests.get(url, headers=headers)

        data = response.json()

        return Response(data)

class MetasImportCsvView(APIView):

    def post(self, request):
        token = request.data.get('token')
        year = request.data.get('year')
        sec_ejec = request.data.get('secEjec')

        url = (
            f"https://apps4.mineco.gob.pe/siafadmapp/privado/registros/metaPresupuestal/"
            f"getListMetaPresupuestal?anoEje={year}&secEjec={sec_ejec}"
            f"&categoria=&programa=&_search=false&nd=1753300853786&rows=10000&page=1&sidx=&sord=asc"
        )

        headers = {"Cookie": f"JSESSIONID={token};"}

        response = requests.get(url, headers=headers)
        data = response.json()

        # Generar archivo CSV (UTF-8 con BOM)
        return self.generate_csv_file(data, year)

    def generate_csv_file(self, data, year):
        # Crear buffer en memoria
        buffer = io.StringIO()
        
        # Escribir BOM para UTF-8
        buffer.write("\ufeff")

        writer = csv.writer(buffer, delimiter=';')

        # Encabezados
        headers = [
            'ano_eje', 'sec_ejec', 'sec_func', 'funcion', 'programa',
            'sub_progra', 'act_proy', 'componente', 'meta', 'finalidad',
            'nombre', 'programa_p', 'pgpto_nom', 'nfuncion', 'nactividad',
            'nprograma', 'nsubprogra', 'ncomponent'
        ]
        writer.writerow(headers)

        # Escribir filas
        for item in data.get('rows', []):
            actProyNombre = str(item.get('actProyNombre', '') or '')[:250]
            finalidadNombre = str(item.get('finalidadNombre', '') or '')[:250]

            row = [
                str(item.get('anoEje', '') or ''),
                str(item.get('secEjec', '') or ''),
                str(item.get('secFunc', '') or ''),
                str(item.get('funcion', '') or ''),
                str(item.get('programa', '') or ''),
                str(item.get('subPrograma', '') or ''),
                str(item.get('actProy', '') or ''),
                str(item.get('componente', '') or ''),
                str(item.get('meta', '') or ''),
                str(item.get('finalidad', '') or ''),
                finalidadNombre,
                str(item.get('programaPpto', '') or ''),
                str(item.get('programaPptoNombre', '') or ''),
                str(item.get('funcionNombre', '') or ''),
                actProyNombre,
                str(item.get('programaNombre', '') or ''),
                str(item.get('subProgramaNombre', '') or ''),
                str(item.get('componenteNombre', '') or ''),
            ]
            writer.writerow(row)

        # Preparar respuesta HTTP como archivo descargable
        response = HttpResponse(
            buffer.getvalue(),
            content_type='text/csv; charset=utf-8'
        )
        response['Content-Disposition'] = f'attachment; filename="metas_{year}.csv"'

        return response

class GlobalBackupView(APIView):

    def get(self, request):

        backups = GlobalBackup.objects.all().order_by("-created_at")
        serializer = GlobalBackupSerializer(backups, many=True)
        return Response(serializer.data)

    def post(self, request):

        user = request.user.username if request.user.is_authenticated else "manual"
        call_command("backup_global", user=user)
        return Response(
            {"message": "Backup global iniciado"},
            status=status.HTTP_201_CREATED
        )
    
class GlobalBackupDownloadView(APIView):

    def get(self, request, backup_id):

        try:
            backup = GlobalBackup.objects.get(id=backup_id)

        except GlobalBackup.DoesNotExist:

            raise Http404("Backup no encontrado")

        if not os.path.exists(backup.file_path):

            raise Http404("Archivo no existe en el servidor")

        response = FileResponse(
            open(backup.file_path, "rb"),
            as_attachment=True,
            filename=backup.file_name
        )

        return response

class TenantBackupView(APIView):

    def get(self, request, tenant_id):

        backups = TenantBackup.objects.filter(
            tenant_id=tenant_id
        ).order_by("-created_at")

        serializer = TenantBackupSerializer(backups, many=True)

        return Response(serializer.data)

    def post(self, request, tenant_id):

        tenant = Client.objects.get(id=tenant_id)
        user = request.user.username if request.user.is_authenticated else "manual"

        call_command(
            "backup_tenant",
            schema=tenant.schema_name,
            user=user
        )

        return Response(
            {"message": "Backup del tenant iniciado"},
            status=201
        )

class TenantBackupDownloadView(APIView):

    def get(self, request, backup_id):

        backup = TenantBackup.objects.get(id=backup_id)

        return FileResponse(
            open(backup.file_path, "rb"),
            as_attachment=True,
            filename=backup.file_name
        )

class MercadoPagoWebhookView(APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        body = request.data

        if body.get("type") != "payment":

           return Response({"ignored": True}, status=200)

        payment_id = body.get("data", {}).get("id")
        if not payment_id:
            return Response({"error": "no payment id"}, status=400)

        r = requests.get(
            f"https://api.mercadopago.com/v1/payments/{payment_id}",
            headers={
                "Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}"
            },
            timeout=10
        )

        if r.status_code != 200:
            return Response({"error": "mp error"}, status=500)

        payment = r.json()

        # 3️⃣ Procesar pago (multitenant)
        self.procesar_pago(payment)

        return Response({"ok": True}, status=200)

    def procesar_pago(self, payment):

        if payment["status"] != "approved":

           return

        ref = payment.get("external_reference")

        if not ref:
            return

        try:

            ref = json.loads(ref)
        
        except Exception:

            return

    
class ProcessPayment(APIView):

    authentication_classes = []
    permission_classes = []

    def post(self, request):

        sdk = mercadopago.SDK(settings.MP_ACCESS_TOKEN)

        payment_data = {
            "transaction_amount": float(request.data['transaction_amount']),
            "installments": int(request.data.get("installments")),
            "token": request.data.get('token'), # Requerido para tarjetas
            "description": "Compra en Mi Tienda",
            "payment_method_id": request.data['payment_method_id'], # 'yape' o id de tarjeta
            "payer": {
                "email": request.data['payer']['email'],
            }
        }

        payment_response = sdk.payment().create(payment_data)
        payment = payment_response["response"]

        return Response(payment)