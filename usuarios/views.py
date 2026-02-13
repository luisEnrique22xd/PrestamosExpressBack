from django.shortcuts import render

# Create your views here.
# usuarios/views.py
from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    # Permitimos que cualquiera acceda a esta URL (si no, nadie podría registrarse)
    permission_classes = (AllowAny,) 
    serializer_class = RegisterSerializer