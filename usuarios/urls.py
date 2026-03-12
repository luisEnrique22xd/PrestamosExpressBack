# usuarios/urls.py
from . import views
from django.urls import path
from .views import RegisterView, perfil_usuario
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    # Ruta para Login (devuelve el Access y Refresh Token)
    path('login/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    
    # Ruta para renovar el Access Token cuando expire
    path('login/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('perfil/', views.perfil_usuario, name='perfil_usuario'),
    path('perfil/actualizar/', views.actualizar_perfil, name='actualizar_perfil'),
    path('perfil/cambiar-password/', views.cambiar_password, name='cambiar_password'),
]