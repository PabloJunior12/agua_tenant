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