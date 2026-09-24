from rest_framework.permissions import BasePermission


class IsNotReadOnly(BasePermission):
    """
    Permite modificar únicamente a usuarios que no sean de solo lectura.
    """

    message = 'Accion no permitida.'

    def has_permission(self, request, view):
        if request.method in ['GET', 'HEAD', 'OPTIONS']:
            return True

        return not request.user.is_readonly