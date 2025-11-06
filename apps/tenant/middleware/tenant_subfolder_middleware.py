from django.db import connection
from django.http import Http404
from django_tenants.utils import get_tenant_model, get_public_schema_name

class TenantSubfolderMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.TenantModel = get_tenant_model()

    def __call__(self, request):
        path = request.path_info.strip("/").split("/")
        tenant_name = None

        # Ejemplo: /clientes/pangoa/admin/
        if len(path) >= 2 and path[0] == "clientes":
            tenant_name = path[1]

        if tenant_name:
            try:
                tenant = self.TenantModel.objects.get(schema_name=tenant_name)
            except self.TenantModel.DoesNotExist:
                raise Http404(f"Tenant '{tenant_name}' no encontrado")
        else:
            # Si no hay subcarpeta, usamos el esquema público
            tenant = self.TenantModel.objects.get(schema_name=get_public_schema_name())

        # 🔹 Asignamos el tenant al request
        request.tenant = tenant

        # 🔹 Cambiamos el schema activo
        connection.set_schema(tenant.schema_name)

        return self.get_response(request)
