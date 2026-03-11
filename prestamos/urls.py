from django.urls import path
from .views import CalendarioPagosView, ClienteDetailView, ClienteListCreateView, EstadisticasDinamicasView, EstadisticasGlobalesView, PrestamoListCreateView, RegistrarAbonoView

urlpatterns = [
    path('clientes/', ClienteListCreateView.as_view(), name='cliente-list'),
    path('prestamos/', PrestamoListCreateView.as_view(), name='prestamo-list'),
    path('clientes/<int:pk>/', ClienteDetailView.as_view(), name='cliente-detail'),
    path('abonos/', RegistrarAbonoView.as_view(), name='registrar-abono'),
    path('estadisticas-globales/', EstadisticasGlobalesView.as_view(), name='stats-globales'),
    path('estadisticas-dinamicas/', EstadisticasDinamicasView.as_view(), name='stats-dinamicas'),
    path('calendario-pagos/', CalendarioPagosView.as_view(), name='calendario-pagos'),
]