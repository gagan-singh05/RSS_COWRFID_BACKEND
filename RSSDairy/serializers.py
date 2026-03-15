from rest_framework import serializers
from .models import RfidScan, Block, Cow

class BlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = Block
        fields = "__all__"

class CowSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cow
        fields = "__all__"

class RfidScanSerializer(serializers.ModelSerializer):
    class Meta:
        model = RfidScan
        fields = "__all__"
