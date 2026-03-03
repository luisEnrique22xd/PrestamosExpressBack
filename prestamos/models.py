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
    # Relación con el Deudor
    cliente = models.ForeignKey(Cliente, on_delete=models.CASCADE, related_name='prestamos')
    # Datos del Préstamo
    monto_capital = models.DecimalField(max_digits=10, decimal_places=2)
    tasa_interes = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    modalidad = models.CharField(max_length=1, choices=MODALIDADES)
    total_cuotas = models.IntegerField()
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    # Información del Aval
    nombre_aval = models.CharField(max_length=200)
    telefono_aval = models.CharField(max_length=15)
    direccion_aval = models.TextField()
    curp_aval = models.CharField(max_length=18, null=True, blank=True)
    parentesco_aval = models.CharField(max_length=50, help_text="Ej. Amigo, Familiar, Vecino")
    garantia_descripcion = models.CharField(max_length=50, help_text="Ej. Laptop")
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    monto_total_pagar = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    def __str__(self):
        return f"Préstamo {self.id} - Cliente: {self.cliente.nombre} | Aval: {self.nombre_aval}"

class Abono(models.Model):
    prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, related_name='abonos')
    monto_pago = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateTimeField(auto_now_add=True)
    numero_cuota = models.IntegerField()