from django.db import models

from usuarios.models import LogSistema


def registrar_log(user, accion, detalle):
    # Validamos que el usuario no sea anónimo
    if user and user.is_authenticated:
        # Solo pasamos los datos, sin definiciones de modelos
        LogSistema.objects.create(
            usuario=user, 
            accion=accion, 
            detalle=detalle
        )
        
class Grupo(models.Model):
    nombre_grupo = models.CharField(max_length=200, verbose_name="Nombre del Grupo")
    integrantes = models.ManyToManyField('Cliente', related_name='mis_grupos')
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre_grupo
            
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
    
    TIPOS = [('I', 'Individual'), ('G', 'Grupal')]
    MODALIDADES = [
        ('S', 'Semanal'),
        ('Q', 'Quincenal'),
        ('M', 'Mensual'),
    ]
    tipo = models.CharField(max_length=1, choices=TIPOS, default='I')
    # Si es individual, se llena 'cliente'. Si es grupal, se llena 'grupo'.
    cliente = models.ForeignKey('Cliente', on_delete=models.CASCADE, null=True, blank=True, related_name='prestamos')
    grupo = models.ForeignKey(Grupo, on_delete=models.SET_NULL, null=True, blank=True, related_name='prestamos')
    # Relación con el Deudor
    # Datos del Préstamo
    monto_capital = models.DecimalField(max_digits=10, decimal_places=2)
    tasa_interes = models.DecimalField(max_digits=5, decimal_places=2, default=10.0)
    modalidad = models.CharField(max_length=1, choices=MODALIDADES)
    cuotas = models.IntegerField()
    fecha_inicio = models.DateTimeField(auto_now_add=True)
    folio_pagare = models.IntegerField(null=True, blank=True)    # Información del Aval
    nombre_aval = models.CharField(max_length=200)
    telefono_aval = models.CharField(max_length=15)
    direccion_aval = models.TextField()
    curp_aval = models.CharField(max_length=18, null=True, blank=True)
    parentesco_aval = models.CharField(max_length=50, help_text="Ej. Amigo, Familiar, Vecino")
    garantia_descripcion = models.CharField(max_length=50, help_text="Ej. Laptop")
    activo = models.BooleanField(default=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    monto_total_pagar = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def save(self, *args, **kwargs):
        # Si el préstamo es nuevo y NO trae folio (por si se registra manual en admin)
        if not self.id and not self.folio_pagare:
            from django.db.models import Max
            max_p = Prestamo.objects.aggregate(Max('folio_pagare'))['folio_pagare__max'] or 0
            self.folio_pagare = max_p + 1
            
        super(Prestamo, self).save(*args, **kwargs)

    def __str__(self):
        # Verificamos si es grupal o individual para evitar el error de 'NoneType'
        if self.tipo == 'G' and self.grupo:
            sujeto = f"GRUPO: {self.grupo.nombre_grupo}"
        elif self.cliente:
            sujeto = f"CLIENTE: {self.cliente.nombre}"
        else:
            sujeto = "Sin asignar"
            
        return f"Folio: {self.folio_pagare} - {sujeto}"


class Abono(models.Model):
    prestamo = models.ForeignKey(Prestamo, on_delete=models.CASCADE, related_name='abonos')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_pago = models.DateField(auto_now_add=True)
    semana_numero = models.IntegerField() # Para saber si es la Sem 1, Sem 2, etc.
    fecha_pago = models.DateField(auto_now_add=True)
    hora_pago = models.TimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs) # Primero guardamos el abono
        
        # Calculamos el total abonado hasta ahora
        prestamo = self.prestamo
        total_abonado = prestamo.abonos.aggregate(models.Sum('monto'))['monto__sum'] or 0
        
        # Si ya cubrió el total, desactivamos el préstamo
        if total_abonado >= prestamo.monto_total_pagar:
            prestamo.activo = False
            prestamo.save()
            # Opcional: Registrar en el log que se liquidó
            registrar_log(None, "LIQUIDACION", f"Préstamo #{prestamo.id} pagado totalmente")

    def __str__(self):
    # Primero verificamos quién es el deudor de forma segura
        if self.prestamo.tipo == 'G' and self.prestamo.grupo:
            deudor = self.prestamo.grupo.nombre_grupo
        elif self.prestamo.cliente:
            deudor = self.prestamo.cliente.nombre
        else:
            deudor = "Deudor desconocido"
        
        return f"Abono {self.id} - {deudor} (${self.monto})"

class Penalizacion(models.Model):
    prestamo = models.ForeignKey('Prestamo', on_delete=models.CASCADE, related_name='penalizaciones')
    monto_penalizado = models.DecimalField(max_digits=10, decimal_places=2)
    fecha_aplicacion = models.DateField(auto_now_add=True)
    descripcion = models.CharField(max_length=255, default="Recargo diario por mora (1.5%)")
    activa = models.BooleanField(default=True) 
    motivo_condonacion = models.TextField(blank=True, null=True)
    fecha_condonacion = models.DateTimeField(blank=True, null=True)
    

    def __str__(self):
        estado = "ACTIVA" if self.activa else "CONDONADA"
        return f"{self.prestamo.cliente.nombre} - {self.fecha_aplicacion} ({estado})"

class ContadorFolio(models.Model):
    numero_actual = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"Folio Actual: {self.numero_actual}"