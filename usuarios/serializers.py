# usuarios/serializers.py
from django.contrib.auth.models import User
from rest_framework import serializers

from usuarios.models import LogSistema

class RegisterSerializer(serializers.ModelSerializer):
    # Definimos el password como write_only para que nunca se envíe de vuelta por la API
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'password', 'email', 'first_name')

    def create(self, validated_data):
        # USAMOS create_user: Esto es vital porque encripta la contraseña automáticamente
        user = User.objects.create_user(
            username=validated_data['username'],
            password=validated_data['password'],
            email=validated_data.get('email', ''),
            first_name=validated_data.get('first_name', '')
        )
        return user
class LogSistemaSerializer(serializers.ModelSerializer):
    # Creamos un campo calculado para ver el nombre real en la tabla
    usuario_nombre = serializers.ReadOnlyField(source='usuario.get_full_name')
    fecha_formateada = serializers.DateTimeField(source='fecha', format="%d/%m/%Y %H:%M", read_only=True)

    class Meta:
        model = LogSistema
        fields = ['id', 'usuario_nombre', 'accion', 'detalle', 'fecha_formateada', 'fecha']
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        # Agregamos el rol a la respuesta JSON
        data['role'] = 'admin' if self.user.is_superuser else 'cobrador'
        data['username'] = self.user.username
        return data