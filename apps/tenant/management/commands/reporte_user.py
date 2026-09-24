from django.core.management.base import BaseCommand
from django_tenants.utils import schema_context

from apps.tenant.models import Client
from apps.user.models import User

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Genera un reporte de usuarios de un tenant"

    def add_arguments(self, parser):
        parser.add_argument(
            "schema_name",
            type=str,
            help="Schema del tenant, por ejemplo: chilca"
        )

    def handle(self, *args, **options):

        schema_name = options["schema_name"]

        # ==========================================================
        # TENANT EN SCHEMA PUBLIC
        # ==========================================================

        tenant = Client.objects.filter(
            schema_name=schema_name
        ).first()

        if not tenant:
            self.stdout.write(
                self.style.ERROR(
                    f"No existe el tenant '{schema_name}'"
                )
            )
            return

        # ==========================================================
        # USUARIOS EN SCHEMA PUBLIC
        # ==========================================================

        usuarios = User.objects.filter(
            tenant=tenant
        ).order_by(
            "name",
            "surname"
        )

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"REPORTE DE USUARIOS - TENANT: {schema_name}"
            )
        )
        self.stdout.write("=" * 120)

        if not usuarios.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No existen usuarios asociados a este tenant."
                )
            )
            return

        # Cabecera
        self.stdout.write(
            f"{'ID':<6}"
            f"{'USERNAME':<25}"
            f"{'NOMBRE':<35}"
            f"{'EMAIL':<40}"
            f"{'ESTADO':<12}"
        )

        self.stdout.write("-" * 120)

        activos = 0
        inactivos = 0

        for usuario in usuarios:

            nombre = f"{usuario.name} {usuario.surname or ''}".strip()

            estado = (
                "ACTIVO"
                if usuario.is_active
                else "INACTIVO"
            )

            if usuario.is_active:
                activos += 1
            else:
                inactivos += 1

            self.stdout.write(
                f"{usuario.id:<6}"
                f"{usuario.username:<25}"
                f"{nombre:<35}"
                f"{usuario.email:<40}"
                f"{estado:<12}"
            )

        self.stdout.write("-" * 120)

        total = usuarios.count()

        self.stdout.write(
            f"TOTAL USUARIOS   : {total}"
        )

        self.stdout.write(
            f"USUARIOS ACTIVOS : {activos}"
        )

        self.stdout.write(
            f"USUARIOS INACTIVOS: {inactivos}"
        )

        self.stdout.write("")