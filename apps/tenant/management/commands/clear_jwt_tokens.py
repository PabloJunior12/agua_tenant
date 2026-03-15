from django.core.management.base import BaseCommand
from django.utils.timezone import now
from rest_framework_simplejwt.token_blacklist.models import (
    OutstandingToken,
    BlacklistedToken
)

class Command(BaseCommand):
    help = "Limpia JWT expirados y blacklist antigua"

    def handle(self, *args, **options):
        expired_tokens = OutstandingToken.objects.filter(expires_at__lt=now())
        count = expired_tokens.count()

        BlacklistedToken.objects.filter(token__in=expired_tokens).delete()
        expired_tokens.delete()

        self.stdout.write(self.style.SUCCESS(
            f"✔️ {count} tokens JWT expirados eliminados"
        ))
