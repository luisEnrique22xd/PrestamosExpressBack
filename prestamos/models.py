from django.db import models

class Cliente(models.Model):
    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=15)
    direccion = models.TextField()
    curp = models.CharField(max_length=18, unique=True)
    fecha_nacimiento = models.DateField()
    # El estatus puede ser calculado o guardado
    es_vencido = models.BooleanField(default=False) 

    def __str__(self):
        return self.nombre

class Aval(models.Model):
    cliente = models.OneToOneField(Cliente, on_delete=models.CASCADE, related_name='aval')
    nombre = models.CharField(max_length=200)
    telefono = models.CharField(max_length=15)
    direccion = models.TextField()

class Prestamo(models.Model):
    MODALIDADES = [
        ('S', 'Semanal'),
        ('Q', 'Quincenal'),
        ('M', 'Mensual'),
    ]
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='prestamos')
    monto_capital = models.DecimalField(max_digits=10, decimal_places=2)
    tasa_interes = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    modalidad = models.CharField(max_length=1, choices=MODALIDADES)
    total_cuotas = models.IntegerField()
    fecha_creacion = models.DateTimeField(auto_now_add=True)

class Abono(models.Model):
    prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, related_name='abonos')
    monto_pago = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    numero_cuota = models.IntegerField()