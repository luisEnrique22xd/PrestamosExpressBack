from django.shortcuts import render
from rest_framework import status
from django.contrib.auth.hashers import check_password
from django.db.models import Max
from rest_framework.decorators import api_view
from rest_framework.response import Response
# Create your views here.
# usuarios/views.py
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAdminUser

from prestamos.models import Abono, Penalizacion, Prestamo
from usuarios.models import LogSistema
from .serializers import LogSistemaSerializer, RegisterSerializer
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
import subprocess
from django.http import HttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAdminUser
from rest_framework import generics
from .models import LogSistema
from prestamos.serializers import HistorialPagosSerializer
from .serializers import LogSistemaSerializer

class ListaLogsView(generics.ListAPIView):
    queryset = LogSistema.objects.all().order_by('-fecha')
    serializer_class = LogSistemaSerializer
    permission_classes = [IsAdminUser]
    
class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    # Permitimos que cualquiera acceda a esta URL (si no, nadie podría registrarse)
    permission_classes = (AllowAny,) 
    serializer_class = RegisterSerializer

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def perfil_usuario(request):
    user = request.user
    abonos_recientes = Abono.objects.all().order_by('-id')[:30]
    tickets_serializer = HistorialPagosSerializer(abonos_recientes, many=True)
    return Response({
        "id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "puesto": "Administrador General" if user.is_superuser else "Cobrador",
        "historial_global": tickets_serializer.data,
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
@api_view(['GET'])
@permission_classes([IsAdminUser])
def export_backup(request):
    try:
        # Generamos un volcado de la base de datos en formato JSON
        # Nota: Asegúrate de que 'python' esté en tu PATH o usa 'sys.executable'
        output = subprocess.check_output(['python', 'manage.py', 'dumpdata', '--indent', '2'])
        
        response = HttpResponse(output, content_type='application/json')
        response['Content-Disposition'] = 'attachment; filename="backup_express_huamantla.json"'
        return response
    except Exception as e:
        from rest_framework.response import Response
        return Response({"error": f"Error al generar backup: {str(e)}"}, status=500)
    
@api_view(['GET'])
def proximo_folio(request):
    # Buscamos el valor máximo actual de folio_pagare
    max_folio = Prestamo.objects.aggregate(Max('folio_pagare'))['folio_pagare__max'] or 0
    return Response({
        "proximo_folio": max_folio + 1
    })
@api_view(['POST'])
def condonar_mora(request):
    mora_id = request.data.get('id_mora')
    try:
        mora = Penalizacion.objects.get(id=mora_id, activa=True)
        prestamo = mora.prestamo
        
        # Restamos la mora del total del préstamo
        prestamo.monto_total_pagar -= mora.monto_penalizado
        mora.activa = False # La "apagamos"
        
        mora.save()
        prestamo.save()
        
        return Response({"message": "Recargos condonados con éxito"})
    except Penalizacion.DoesNotExist:
        return Response({"error": "No hay recargos activos con ese ID"}, status=404)
from rest_framework_simplejwt.views import TokenObtainPairView
from .serializers import MyTokenObtainPairSerializer

class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer