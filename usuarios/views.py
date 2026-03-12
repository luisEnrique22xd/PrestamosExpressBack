from django.shortcuts import render
from rest_framework import status
from django.contrib.auth.hashers import check_password
# Create your views here.
# usuarios/views.py
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    # Permitimos que cualquiera acceda a esta URL (si no, nadie podría registrarse)
    permission_classes = (AllowAny,) 
    serializer_class = RegisterSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def perfil_usuario(request):
    user = request.user
    return Response({
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "puesto": "Administrador General" if user.is_superuser else "Cobrador",
        "last_login": user.last_login.strftime('%I:%M %p') if user.last_login else "N/A"
    })
@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def actualizar_perfil(request):
    user = request.user
    # Actualizamos solo los campos permitidos
    user.first_name = request.data.get('first_name', user.first_name)
    user.last_name = request.data.get('last_name', user.last_name)
    user.email = request.data.get('email', user.email)
    user.save()
    return Response({"message": "Perfil actualizado con éxito"})

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def cambiar_password(request):
    user = request.user
    old_password = request.data.get('old_password')
    new_password = request.data.get('new_password')

    # 1. Validar contraseña actual
    if not check_password(old_password, user.password):
        return Response({"error": "La contraseña actual es incorrecta"}, status=status.HTTP_400_BAD_REQUEST)
    
    # 2. Guardar nueva contraseña (esto la encripta automáticamente)
    user.set_password(new_password)
    user.save()
    return Response({"message": "Contraseña actualizada correctamente"})