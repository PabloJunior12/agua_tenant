# core/permissions.py

from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework import status

class GlobalPermissionMixin:
    
    """Verifica si el usuario tiene un permiso global específico."""

    required_action = None  # Ej: "delete", "edit", etc.

    def check_global_permission(self, request):

        user = request.user

        # Solo si tiene GlobalPermission asociado

        if hasattr(user, "global_permissions"):

            allowed = user.global_permissions.allowed_actions or []

            if self.required_action and self.required_action not in allowed:

               raise PermissionDenied(f"No tienes permiso para la accion de {self.required_action}")
            
        else:

            raise PermissionDenied("No tienes permisos globales configurados.")
        
