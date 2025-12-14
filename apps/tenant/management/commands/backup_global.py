import os
import subprocess
from django.core.management.base import BaseCommand
from django.conf import settings
from apps.tenant.models import GlobalBackup
from datetime import datetime
from pathlib import Path

class Command(BaseCommand):

    help = "Backup global de todos los schemas (django-tenants)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user",
            type=str,
            help="Usuario que ejecuta el backup"
        )

    def handle(self, *args, **options):

        backup_dir = Path(settings.BACKUP_GLOBAL_PATH)
        backup_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now().strftime("%Y-%m-%d_%H-%M")
        file_name = f"backup_global_{today}.dump"
        file_path = backup_dir / file_name

        db = settings.DATABASES["default"]
        env = os.environ.copy()
        env["PGPASSWORD"] = db["PASSWORD"]

        backup = GlobalBackup.objects.create(
            file_name=file_name,
            file_path=str(file_path),
            status="pending",
            created_by=options.get("user") or "cron"
        )

        try:
            # 4️⃣ Ejecutar pg_dump
            subprocess.run([
                "pg_dump",
                "-h", db["HOST"],
                "-U", db["USER"],
                "-F", "c",
                "-f", str(file_path),
                db["NAME"]
            ], env=env, check=True)

            # 5️⃣ Tamaño
            size_mb = file_path.stat().st_size / (1024 * 1024)

            backup.status = "success"
            backup.size_mb = round(size_mb, 2)
            backup.save()

            self.stdout.write(
                self.style.SUCCESS("Backup global generado correctamente")
            )

        except Exception as e:
            backup.status = "failed"
            backup.save()
            self.stderr.write(str(e))