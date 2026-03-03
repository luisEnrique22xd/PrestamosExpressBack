from django.urls import path
from .views import ClienteListCreateView, PrestamoListCreateView

urlpatterns = [
    path('clientes/', ClienteListCreateView.as_view(), name='cliente-list'),
    path('prestamos/', PrestamoListCreateView.as_view(), name='prestamo-list'),
]