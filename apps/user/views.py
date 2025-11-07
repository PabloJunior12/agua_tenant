from django.contrib.auth import authenticate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework import status
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import PageNumberPagination
from .serializers import UserSerializer, ModuleSerializer, UserPermissionSerializer
from .models import User, Module, UserPermission
from django.conf import settings
from django.db import connection
import requests

class CustomPagination(PageNumberPagination):

    page_size = 5  # Número de registros por página
    page_size_query_param = 'page_size'  # Permite cambiar el tamaño desde la URL
    max_page_size = 100  # Tamaño máximo permitido

class LoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')
        tenant_name = request.data.get('tenant')

        if not username or not password:
            return Response({"error": "Se requieren usuario y password."}, status=400)

        user = authenticate(request, username=username, password=password)

        if user is None:
            return Response({"error": "Credenciales invalidas."}, status=401)

        if not user.is_active:
            return Response({"error": "Cuenta desactivada."}, status=403)

    
        tenant_name = (tenant_name or "").lower().strip()

 
        if tenant_name == "public":
            if user.tenant:
                return Response(
                    {"error": "Este usuario pertenece a un tenant y no puede acceder al entorno publico."},
                    status=403
                )

   
        else:
            if not user.tenant:
                return Response(
                    {"error": "Este usuario es global y no pertenece a ningun tenant."},
                    status=403
                )

            if user.tenant.schema_name != tenant_name:
                return Response(
                    {"error": f"El usuario no pertenece al tenant '{tenant_name}'."},
                    status=403
                )

   
        token, _ = Token.objects.get_or_create(user=user)
        permissions = UserPermission.objects.filter(user=user).select_related('module')

        permissions_data = [
            {"module_id": perm.module.id, "module": perm.module.code, "name": perm.module.name}
            for perm in permissions
        ]

        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "is_admin": user.is_admin,
            "is_staff": user.is_staff,
            "tenant": user.tenant.schema_name if user.tenant else "public",
            "token": token.key,
            "permissions": permissions_data,
        }

        return Response(user_data, status=200)
      
class LogoutView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        try:
             
            request.user.auth_token.delete()
            return Response({"message": "Logout exitoso."}, status=200)
        
        except:

             return Response({"error": "Error al realizar el logout."}, status=400)

class ProtectedView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        return Response({"message": "Accediste a una ruta protegida"}, status=200)
    
class RucApiView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, number):

        # Construcción del endpoint y encabezados
        url = f"https://apifoxperu.net/api/ruc/{number}"
        token = "LFn46Swn6FyiDG5MwGzjMAeZXxp3MLPi1P9W9njJ"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Solicitud al servicio externo
            response = requests.get(url, headers=headers, timeout=10)

            # Validar respuesta
            if response.status_code == 200:
                return Response(response.json())
            else:
                return Response(
                    {"error": f"Error al consultar el servicio externo. details {response.json()}"}, status=response.status_code,
                )
        except requests.RequestException as e:
            # Manejo de excepciones en caso de error de conexión o tiempo de espera
            return Response(
                {"error": f"Error al conectar con el servicio externo. details {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        
class DniApiView(APIView):

    permission_classes = [IsAuthenticated]
    
    def get(self, request, number):

        # Construcción del endpoint y encabezados
        url = f"https://apifoxperu.net/api/dni/{number}"
        token = "LFn46Swn6FyiDG5MwGzjMAeZXxp3MLPi1P9W9njJ"
        headers = {"Authorization": f"Bearer {token}"}

        try:
            # Solicitud al servicio externo
            response = requests.get(url, headers=headers, timeout=10)

            # Validar respuesta
            if response.status_code == 200:
                return Response(response.json())
            else:
                return Response(
                    response.json(), status=response.status_code,
                )
        except requests.RequestException as e:
            # Manejo de excepciones en caso de error de conexión o tiempo de espera
            return Response(
                {"error": f"Error al conectar con el servicio externo. details {str(e)}"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        
class UserViewSet(ModelViewSet):

    queryset = User.objects.all().order_by('id')
    serializer_class = UserSerializer
    pagination_class = CustomPagination

    def get_queryset(self):

        user = self.request.user

        # 🧩 Superusuario global (staff=True, tenant=None)
        if user.is_staff and user.tenant is None:
            return User.objects.all().order_by('id')

        # 🧩 Administrador de tenant (is_admin=True, tenant=X)
        elif user.is_admin and user.tenant is not None:
            return User.objects.filter(tenant=user.tenant).exclude(is_staff=True).order_by('id')

        # 🧩 Usuario normal (solo si quieres permitirle verse a sí mismo)
        # elif not user.is_admin and user.tenant is not None:
        #     return User.objects.filter(id=user.id)

        # 🧩 Cualquier otro caso
        return User.objects.none()

class ModuleViewSet(ModelViewSet):

    queryset = Module.objects.all().order_by('id')
    serializer_class = ModuleSerializer

class UserPermissionViewSet(ModelViewSet):

    queryset = UserPermission.objects.all()
    serializer_class = UserPermissionSerializer

    def get_queryset(self):

        user_id = self.request.query_params.get('user')
        if user_id:
            return UserPermission.objects.filter(user_id=user_id)
        return super().get_queryset()

class MeView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        
        user = request.user

        # Obtener permisos del usuario
        permissions = UserPermission.objects.filter(user=user).select_related('module')

        permissions_data = [
            {
                "module_id": perm.module.id,
                "module": perm.module.code,
                "name": perm.module.name,
            }
            for perm in permissions
        ]

        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "is_admin": user.is_admin,
            "is_staff": user.is_staff,
            "tenant": user.tenant.id if user.tenant else None,
            "permissions": permissions_data,
        }

        return Response(user_data, status=200)