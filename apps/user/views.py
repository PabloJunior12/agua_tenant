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
from .services import get_allowed_modules, user_has_activity
import requests
from rest_framework_simplejwt.tokens import RefreshToken

class CustomPagination(PageNumberPagination):

    page_size = 5  # Número de registros por página
    page_size_query_param = 'page_size'  # Permite cambiar el tamaño desde la URL
    max_page_size = 100  # Tamaño máximo permitido

class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username")
        password = request.data.get("password")
        tenant_name = request.data.get("tenant")

        if not username or not password:
            return Response({"error": "Se requieren usuario y contraseña."}, status=400)

        user = authenticate(username=username, password=password)

        if not user:
            return Response({"error": "Credenciales inválidas."}, status=401)

        if not user.is_active:
            return Response({"error": "Cuenta desactivada."}, status=403)

        tenant_name = (tenant_name or "").lower().strip()

        # 🔒 Validación tenant
        if tenant_name == "public":
            if user.tenant:
                return Response(
                    {"error": "Este usuario pertenece a un tenant."},
                    status=403
                )
        else:
            if not user.tenant:
                return Response(
                    {"error": "Usuario global no permitido en tenant."},
                    status=403
                )
            if user.tenant.schema_name != tenant_name:
                return Response(
                    {"error": f"Tenant '{tenant_name}' inválido."},
                    status=403
                )

        # ✅ Tokens JWT
        refresh = RefreshToken.for_user(user)

        permissions = UserPermission.objects.filter(
            user=user
        ).select_related("module")

        permissions_data = [
            {
                "module_id": p.module.id,
                "module": p.module.code,
                "name": p.module.name
            }
            for p in permissions
        ]

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "username": user.username,
                "name": user.name,
                "is_admin": user.is_admin,
                "is_staff": user.is_staff,
                "tenant": user.tenant.schema_name if user.tenant else "public",
                "permissions": permissions_data
            }
        }, status=200)
      
class LogoutView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh")

        if refresh:
            try:
                token = RefreshToken(refresh)
                token.blacklist()
            except Exception:
                pass  # token expirado o inválido → ignorar

        return Response({"message": "Logout OK"}, status=200)
        
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

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()

        if user_has_activity(user):
            # Tiene actividad → NO se borra
            # user.is_active = False
            # user.save(update_fields=["is_active"])

            return Response(
                {"error": "Usuario desactivado (tiene registros)"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ❗ Caso válido para borrado físico
        user.delete()

        return Response(
            {"message": "Usuario eliminado definitivamente"},
            status=status.HTTP_200_OK
        )

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

        # módulos permitidos (incluye padres)
        root_modules = get_allowed_modules(user)
        module_tree = ModuleSerializer(root_modules, many=True).data

        user_data = {
            "id": user.id,
            "username": user.username,
            "name": user.name,
            "is_admin": user.is_admin,
            "is_staff": user.is_staff,
            "tenant": user.tenant.id if user.tenant else None,
            "modules": module_tree,
        }

        return Response(user_data, status=200)