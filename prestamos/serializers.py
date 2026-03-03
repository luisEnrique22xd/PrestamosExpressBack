from rest_framework import serializers
from .models import Cliente, Prestamo

# Este es el que te falta según el error
class ClienteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cliente
        fields = '__all__'

# Este es el que agregamos para los préstamos
class PrestamoSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.ReadOnlyField(source='cliente.nombre')

    class Meta:
        model = Prestamo
        fields = [
            'id', 'cliente', 'cliente_nombre', 'monto_capital', 
            'monto_total_pagar', 'total_cuotas', 'modalidad', 'fecha_inicio',
            'nombre_aval', 'telefono_aval', 'direccion_aval', 
            'curp_aval', 'parentesco_aval', 'activo','garantia_descripcion'
        ]