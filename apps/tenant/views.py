from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, viewsets
from django.contrib.auth import authenticate
from django_tenants.utils import schema_context, get_tenant_model
from .models import Client
from .serializers import ClientSerializer
from apps.user.models import User,UserPermission, Module
from django.db import connection, transaction
from apps.agua.models import Company
from .utils.seed import load_initial_data
from bs4 import BeautifulSoup
import csv
import io
import requests
from django.http import HttpResponse

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

    def get(self, request):

        # Crear sesion real por usuario
        session = requests.Session()
        request.session["mineco"] = session.cookies.get_dict()

        captcha_url = "https://apps4.mineco.gob.pe/siafadmapp/jcaptcha.jpg"
        captcha_response = session.get(captcha_url)

        print(">>> COOKIES INICIALES:", session.cookies.get_dict())

        if captcha_response.status_code == 200:
            import base64
            b64 = base64.b64encode(captcha_response.content).decode("utf-8")
            return Response({"captcha": b64})
        else:
            return Response({"error": "Error al descargar captcha"}, status=400)


    def post(self, request):

        # 1 — Crear la sesión REAL (si no existe)
        session = requests.Session()

        username = request.data.get("username")
        password = request.data.get("password")
        captcha = request.data.get("captcha")

        login_url = "https://apps4.mineco.gob.pe/siafadmapp/j_spring_security_check"

        payload = {
            "j_username": username,
            "j_password": password,
            "jcaptcha": captcha,
            "btnIngresar": "Ingresar"
        }

        # 2 — LOGIN REAL
        login_resp = session.post(login_url, data=payload, allow_redirects=True)

        print("\n>>> COOKIES DESPUÉS DEL LOGIN:")
        print(session.cookies.get_dict())

        # 3 — Verificar todas las cookies importantes
        cookies = session.cookies.get_dict()

        if "JSESSIONID" not in cookies:
            return Response({"error": "No se generó JSESSIONID"}, status=400)

        # 4 — Consumir el menú USANDO LA MISMA SESIÓN
        menu_url = "https://apps4.mineco.gob.pe/siafadmapp/privado/menu"

        menu_resp = session.get(menu_url)

        print("\n>>> HTML DEL MENÚ:", menu_resp.text[:200])

        # 5 — Validar si Imperva devolvió login
        if "Inicio de sesión" in menu_resp.text:
            return Response({"error": "Sesión inválida (Imperva bloqueó la entrada)"}, status=400)

        # 6 — ÉXITO
        return Response({
            "status": "OK",
            "cookies": cookies
        })
    
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