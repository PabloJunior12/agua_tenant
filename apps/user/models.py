from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from apps.tenant.models import Client
import uuid

class CustomUserManager(BaseUserManager):
    def create_user(self, email, username, password=None, **extra_fields):
        if not email:
            raise ValueError('El email es obligatorio')
        if not username:
            raise ValueError('El username es obligatorio')

        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, username=username, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, username, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('El superusuario debe tener is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('El superusuario debe tener is_superuser=True.')

        return self.create_user(email, username, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):

    name = models.CharField(max_length=150, blank=True)
    surname = models.CharField(max_length=150, blank=True, null=True)
    email = models.EmailField(unique=True)
    username = models.CharField(max_length=150, unique=True)  # Nuevo campo username
    phone = models.CharField(max_length=15, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_admin = models.BooleanField(default=False) 

    objects = CustomUserManager()
    yape_token = models.CharField(max_length=64, blank=True, null=True)
    tenant = models.ForeignKey(Client, blank=True, null=True, on_delete=models.SET_NULL)

    USERNAME_FIELD = 'username'  # <<< Cambiar a username como identificador principal
    REQUIRED_FIELDS = ['email', 'name']  # Email ahora es campo obligatorio adicional

    def __str__(self):
        
        return self.username
    
    def generar_token_yape(self):

        self.yape_token = uuid.uuid4().hex  # genera un token único
        self.save()
        return self.yape_token

class Module(models.Model):

    name = models.CharField(max_length=100)
    path = models.CharField(max_length=100, blank=True, null=True)
    code = models.CharField(max_length=50, unique=True)  # ejemplo: "lecturas", "facturacion"
    icon = models.CharField(max_length=50, blank=True, null=True)  # opcional para el menú
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        related_name="children",
        blank=True,
        null=True
    )

    def __str__(self):
        return self.name

class UserPermission(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='permissions')
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='user_permissions')


    class Meta:
        unique_together = ('user', 'module')

    def __str__(self):
        return f"{self.user.username} - {self.module.code}"

class GlobalPermission(models.Model):
    
    ACTION_CHOICES = [
        ('view', 'Ver'),
        ('create', 'Crear'),
        ('edit', 'Editar'),
        ('delete', 'Eliminar'),
        ('charge', 'Cobrar'),
        ('export', 'Exportar'),
        ('approve', 'Aprobar'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='global_permissions')
    allowed_actions = models.JSONField(default=list)

    def __str__(self):
        return f"Permisos globales de {self.user.username}"
