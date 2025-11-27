
from .models import User, Module, UserPermission

def get_allowed_modules(user):
    # módulos del usuario
    module_ids = list(
        UserPermission.objects.filter(user=user)
        .values_list("module_id", flat=True)
    )

    # incluir padres automáticamente
    allowed = set(module_ids)

    def add_parents(module):
        if module.parent:
            allowed.add(module.parent.id)
            add_parents(module.parent)

    for module in Module.objects.filter(id__in=module_ids):
        add_parents(module)

    # devolver módulos raíz
    return Module.objects.filter(id__in=allowed, parent__isnull=True).order_by("order")