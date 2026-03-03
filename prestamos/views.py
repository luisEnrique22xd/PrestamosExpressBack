# prestamos/views.py
from rest_framework import generics
from .models import Cliente, Prestamo
from .serializers import ClienteSerializer, PrestamoSerializer

# Vista para Clientes (La que ya tenías)
class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

# NUEVA Vista para Préstamos
class PrestamoListCreateView(generics.ListCreateAPIView):
    queryset = Prestamo.objects.all().order_by('-id')
    serializer_class = PrestamoSerializer