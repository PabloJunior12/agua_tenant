from datetime import timedelta
from django.utils import timezone
from django.core.management.base import BaseCommand
from apps.tenant.models import GlobalBackup, TenantBackup
import os

class Command(BaseCommand):
    help = "Elimina backups antiguos"

    def handle(self, *args, **options):
        now = timezone.now()

        for backup in GlobalBackup.objects.filter(
            created_at__lt=now - timedelta(days=7)
        ):
            if os.path.exists(backup.file_path):
                os.remove(backup.file_path)
            backup.delete()

        for backup in TenantBackup.objects.filter(
            created_at__lt=now - timedelta(days=14)
        ):
            if os.path.exists(backup.file_path):
                os.remove(backup.file_path)
            backup.delete()

        self.stdout.write("Backups antiguos eliminados")
