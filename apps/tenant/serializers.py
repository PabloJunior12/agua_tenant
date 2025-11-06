# apps/tenants/api/serializers.py
from rest_framework import serializers
from .models import Client

class ClientSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Client
        fields = ['id', 'schema_name','created_at']
        read_only_fields = ['id', 'schema_name', 'created_at']
