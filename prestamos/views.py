from django.shortcuts import render

# Create your views here.
from rest_framework import generics
from .models import Cliente
from .serializers import ClienteSerializer

class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    # Solo usuarios logueados pueden ver/crear clientes