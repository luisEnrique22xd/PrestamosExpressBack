from django.contrib import admin

from prestamos.models import Cliente, Prestamo

# Register your models here.
# Registramos los modelos
admin.site.register(Cliente)
admin.site.register(Prestamo)