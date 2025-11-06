from django.contrib.auth import get_user_model
from django_tenants.middleware.main import TenantMainMiddleware

class PublicUserMiddleware(TenantMainMiddleware):
    def process_request(self, request):
        # Mantiene el schema normal
        super().process_request(request)
        
        # Si viene un token o sesión, buscamos el user en public
        user = None
        if request.user.is_authenticated:
            # Aquí siempre apunta a public
            User = get_user_model()
            try:
                user = User.objects.using('default').get(pk=request.user.pk)
                request.user = user
            except User.DoesNotExist:
                pass
        return None
