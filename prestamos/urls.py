from django.urls import path

from usuarios.views import proximo_folio
from .views import CalendarioPagosView, ClienteDetailView, ClienteListCreateView, EstadisticasDinamicasView, PrestamoListCreateView, RegistrarAbonoView, cartera_vencida_hibrida, detalle_grupo, directorio_hibrido, estadisticas_globales
from prestamos import views

urlpatterns = [
    path('clientes/', ClienteListCreateView.as_view(), name='cliente-list'),
    path('prestamos/', PrestamoListCreateView.as_view(), name='prestamo-list'),
    path('clientes/<int:pk>/', ClienteDetailView.as_view(), name='cliente-detail'),
    path('abonos/', RegistrarAbonoView.as_view(), name='registrar-abono'),
     path('estadisticas-globales/', estadisticas_globales),
    path('estadisticas-dinamicas/', EstadisticasDinamicasView.as_view(), name='stats-dinamicas'),
    path('calendario-pagos/', CalendarioPagosView.as_view(), name='calendario-pagos'),
    path('clientes/directorio-hibrido/', directorio_hibrido, name='directorio-hibrido'),
    path('grupos/<int:pk>/detalle/', detalle_grupo, name='detalle-grupo'),
    path('prestamos/cartera-vencida/', cartera_vencida_hibrida, name='cartera-vencida'),
    path('proximo-folio/', proximo_folio, name='proximo-folio'),
    path('penalizaciones/<int:pk>/condonar/', views.condonar_mora, name='condonar-mora'),
    
]