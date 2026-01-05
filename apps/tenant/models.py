
# tenants/models.py
from django.db import models
from django_tenants.models import TenantMixin, DomainMixin
from datetime import timedelta
from django.utils.timezone import now

class Client(TenantMixin):

    created_at = models.DateTimeField(auto_now_add=True)

    # Django-tenants creará el schema automáticamente
    auto_create_schema = True
    auto_drop_schema = True

    # 🔐 Control de servicio
    is_active = models.BooleanField(default=True)
    payment_due_date = models.DateField()
    grace_days = models.PositiveIntegerField(default=5)

    def is_payment_overdue(self):
        return now().date() > self.payment_due_date + timedelta(days=self.grace_days)

    def __str__(self):
        return self.schema_name

class Domain(DomainMixin):

    pass

class GlobalBackup(models.Model):

    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("success", "Exitoso"),
        ("failed", "Fallido"),
    )

    file_name = models.CharField(max_length=255)
    file_path = models.TextField()
    size_mb = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Usuario o CRON"
    )

    def __str__(self):
        
        return self.file_name

class TenantBackup(models.Model):
    
    STATUS_CHOICES = (
        ("pending", "Pendiente"),
        ("success", "Exitoso"),
        ("failed", "Fallido"),
    )

    tenant = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="backups"
    )

    file_name = models.CharField(max_length=255)
    file_path = models.TextField()
    size_mb = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.tenant.schema_name} - {self.created_at}"
    
class Pay(models.Model):
    
    payment_id = models.CharField(max_length=50, unique=True)
    tenant = models.CharField(max_length=50, db_index=True)
    status = models.CharField(max_length=30)
    payment_method = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    raw = models.JSONField()
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
