from django.contrib import admin
from .models import User

@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("username", "email", "phone", "yape_token")

    def save_model(self, request, obj, form, change):
        if not obj.yape_token:
            obj.generar_token_yape()
        super().save_model(request, obj, form, change)