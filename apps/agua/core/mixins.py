# mixins.py
class TenantSafeMixin:
    """
    Mixin para ViewSets que captura cualquier kwargs extra (como tenant_name)
    y los ignora, evitando errores TypeError en métodos de acciones.
    """
    def dispatch(self, request, *args, **kwargs):
        # Eliminamos 'tenant_name' si existe, para que no rompa las acciones
        kwargs.pop('tenant_name', None)
        return super().dispatch(request, *args, **kwargs)
