
# tenants/models.py
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin

class Client(TenantMixin):

    created_at = models.DateTimeField(auto_now_add=True)

    # Django-tenants creará el schema automáticamente
    auto_create_schema = True
    auto_drop_schema = True

    def __str__(self):
        return self.name

class Domain(DomainMixin):

    pass