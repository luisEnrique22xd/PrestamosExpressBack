from django.contrib import admin

from prestamos.models import Cliente, Prestamo

# Register your models here.
# Registramos los modelos
admin.site.register(Cliente)
admin.site.register(Prestamo)
# prestamos/admin.py
from django.contrib import admin
from .models import Penalizacion

@admin.register(Penalizacion)
class PenalizacionAdmin(admin.ModelAdmin):
    # Columnas que se verán en la lista principal
    list_display = ('id', 'get_cliente', 'monto_penalizado', 'fecha_aplicacion', 'prestamo', )
    
    # Filtros laterales para búsqueda rápida
    list_filter = ('fecha_aplicacion', 'prestamo__cliente__nombre')
    
    # Buscador por nombre de cliente e ID de préstamo
    search_fields = ('prestamo__cliente__nombre', 'prestamo__id')
    
    # Ordenar por lo más reciente primero
    ordering = ('-fecha_aplicacion',)

    # Método para mostrar el nombre del cliente directamente en la lista
    def get_cliente(self, obj):
        return obj.prestamo.cliente.nombre
    get_cliente.short_description = 'Cliente'