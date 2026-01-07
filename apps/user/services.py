
from .models import User, Module, UserPermission
from apps.tenant.models import Client
from django_tenants.utils import schema_context
from apps.agua.models import CashBox, ReadingGeneration

USER_ACTIVITY_MODELS = [
    (CashBox, "user_id"),
    (ReadingGeneration, "created_by")
]

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

def user_has_activity(user):
    """
    True = NO se puede borrar
    False = se puede borrar
    """

    # Usuario global (staff / sistema)
    if user.tenant is None:
        return True  # nunca borrar

    with schema_context(user.tenant.schema_name):
        for model, field in USER_ACTIVITY_MODELS:
            filters = {field: user.id}
            if model.objects.filter(**filters).exists():
                return True

    return False

 