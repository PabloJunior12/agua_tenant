from pathlib import Path
from datetime import datetime
import subprocess
import os

from django.core.management.base import BaseCommand
from django.conf import settings
from apps.tenant.models import TenantBackup, Client

class Command(BaseCommand):
    help = "Backup por empresa (tenant)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            type=str,
            help="Schema del tenant (opcional)"
        )
        parser.add_argument(
            "--user",
            type=str,
            default="cron"
        )

    def handle(self, *args, **options):

        db = settings.DATABASES["default"]

        env = os.environ.copy()
        env["PGPASSWORD"] = db["PASSWORD"]

        schema_filter = options.get("schema")

        tenants = Client.objects.all()
        if schema_filter:
            tenants = tenants.filter(schema_name=schema_filter)

        for tenant in tenants:

            backup_dir = (
                Path(settings.BACKUP_TENANT_PATH) / tenant.schema_name
            )
            backup_dir.mkdir(parents=True, exist_ok=True)

            today = datetime.now().strftime("%Y-%m-%d_%H-%M")
            file_name = f"backup_{tenant.schema_name}_{today}.dump"
            file_path = backup_dir / file_name

            backup = TenantBackup.objects.create(
                tenant=tenant,
                file_name=file_name,
                file_path=str(file_path),
                status="pending",
                created_by=options["user"]
            )

            try:
                subprocess.run([
                    "pg_dump",
                    "-h", db["HOST"],
                    "-U", db["USER"],
                    "-n", tenant.schema_name,
                    "-F", "c",
                    "-f", str(file_path),
                    db["NAME"]
                ], env=env, check=True)

                size_mb = file_path.stat().st_size / (1024 * 1024)

                backup.status = "success"
                backup.size_mb = round(size_mb, 2)
                backup.save()

                self.stdout.write(
                    self.style.SUCCESS(
                        f"Backup OK: {tenant.schema_name}"
                    )
                )

            except Exception as e:
                backup.status = "failed"
                backup.save()
                self.stderr.write(
                    f"Error en {tenant.schema_name}: {e}"
                )
