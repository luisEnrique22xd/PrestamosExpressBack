from django.db import models

# Create your models here.

from django.db import models
from django.contrib.auth.models import User

class LogSistema(models.Model):
    # Usamos SET_NULL por si borras a un usuario, no se borre el registro de lo que hizo
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='logs')
    accion = models.CharField(max_length=100) # Ej: "CREACION_PRESTAMO", "PAGO_REGISTRADO"
    detalle = models.TextField() # Ej: "Se registró pago de $500 para el préstamo #45"
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-fecha']
        verbose_name = "Log del Sistema"
        verbose_name_plural = "Logs del Sistema"

    def __str__(self):
        return f"{self.usuario} - {self.accion} - {self.fecha}"