# apps/tenants/api/serializers.py
from rest_framework import serializers
from .models import Client, GlobalBackup, TenantBackup, ReceiptBatch


class ReceiptBatchSerializer(serializers.ModelSerializer):
    
    class Meta:
        
        model = ReceiptBatch
        fields = "__all__"

class ClientSerializer(serializers.ModelSerializer):
    
    class Meta:
        model = Client
        fields = ['id', 'schema_name','created_at']
        read_only_fields = ['id', 'schema_name', 'created_at']

class GlobalBackupSerializer(serializers.ModelSerializer):

    class Meta:
        
        model = GlobalBackup
        fields = "__all__"

class TenantBackupSerializer(serializers.ModelSerializer):
    
    tenant_name = serializers.CharField(
        source="tenant.schema_name",
        read_only=True
    )

    class Meta:
        model = TenantBackup
        exclude = ["file_path"]
