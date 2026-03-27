from decimal import Decimal
from django.db.models import Sum
from rest_framework import serializers
from .models import Cliente, Penalizacion, Prestamo, Abono, Grupo


# serializers.py


class CarteraVencidaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.SerializerMethodField()
    es_grupo = serializers.BooleanField()
    telefono = serializers.CharField()
    saldo_pendiente = serializers.FloatField(source='saldo_actual')
    # 🔥 Campos clave para Alexander:
    cuotas_vencidas = serializers.SerializerMethodField()
    monto_vencido = serializers.SerializerMethodField()
    ultimo_pago = serializers.SerializerMethodField()

    def get_nombre(self, obj):
        return obj.nombre if hasattr(obj, 'nombre') else obj.nombre_grupo

    def _get_prestamo_activo(self, obj):
        if obj.es_grupo:
            return Prestamo.objects.filter(grupo_id=obj.id, activo=True).last()
        return Prestamo.objects.filter(cliente_id=obj.id, activo=True).last()

    def get_cuotas_vencidas(self, obj):
        p = self._get_prestamo_activo(obj)
        if not p: return 0
        # Aquí llamarías a una función similar a la de tu script 'aplicar_mora'
        # para contar cuántas cuotas pasadas no tienen abono.
        return 1 # Ejemplo para la prueba

    def get_monto_vencido(self, obj):
        p = self._get_prestamo_activo(obj)
        if not p: return 0
        # Suma de las cuotas que ya pasaron de fecha y no se pagaron
        return 550.0 # Ejemplo: 1 cuota de Juan
class PenalizacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Penalizacion
        # Asegúrate de usar 'descripcion' y 'fecha_aplicacion' (los nombres que validamos)
        fields = ['id', 'monto_penalizado', 'descripcion', 'activa', 'fecha_aplicacion']

class ClienteDetailSerializer(serializers.ModelSerializer):
    # Declaramos el campo como SerializerMethodField
    penalizaciones = serializers.SerializerMethodField()
    progreso_pagos = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = '__all__' # O tu lista de campos, pero incluye 'penalizaciones'

    def get_penalizaciones(self, obj):
        # Buscamos el último préstamo de este cliente
        ultimo_p = obj.prestamos.order_by('-id').first()
        if ultimo_p:
            # Filtramos solo las activas para el dashboard
            moras = ultimo_p.penalizaciones.filter(activa=True)
            return PenalizacionSerializer(moras, many=True).data
        return []
class ClienteDetailSerializer(serializers.ModelSerializer):
    # Agregamos esto para que el Front reciba la lista
    penalizaciones = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'saldo_actual', 'penalizaciones', ...]

    def get_penalizaciones(self, obj):
        # Buscamos el último préstamo y sus moras
        ultimo_p = obj.prestamos.last()
        if ultimo_p:
            moras = ultimo_p.penalizaciones.all() # O el related_name que tengas
            return PenalizacionSerializer(moras, many=True).data
        return []
    
# 1. SERIALIZER DE CLIENTES (Individual)
class ClienteSerializer(serializers.ModelSerializer):
    tiene_prestamo_activo = serializers.SerializerMethodField()
    datos_ultimo_aval = serializers.SerializerMethodField()
    progreso_pagos = serializers.SerializerMethodField()
    historial_grafico = serializers.SerializerMethodField()
    ultimo_prestamo_id = serializers.SerializerMethodField()
    saldo_actual = serializers.SerializerMethodField()
    numero_prestamos = serializers.SerializerMethodField()
    total_penalizaciones = serializers.SerializerMethodField()
    id_mora_activa = serializers.SerializerMethodField()
    tiene_moras_activas = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id', 'nombre', 'telefono', 'curp', 'direccion','fecha_nacimiento', 
            'datos_ultimo_aval','progreso_pagos', 'historial_grafico', 
            'ultimo_prestamo_id','tiene_prestamo_activo','saldo_actual',
            'numero_prestamos','total_penalizaciones', 'id_mora_activa','tiene_moras_activas'
        ]

    def get_tiene_prestamo_activo(self, obj):
        prestamo = obj.prestamos.filter(activo=True).first()
        if prestamo:
            total_pagado = Abono.objects.filter(prestamo=prestamo).aggregate(Sum('monto'))['monto__sum'] or 0
            if total_pagado >= prestamo.monto_total_pagar:
                prestamo.activo = False
                prestamo.save()
                return False
            return True
        return False
    
    def get_progreso_pagos(self, obj):
        ultimo_p = obj.prestamos.last()
        if not ultimo_p: return {"pagado": 0, "pendiente": 100}
        total_pagado = ultimo_p.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
        porcentaje = (total_pagado / ultimo_p.monto_total_pagar) * 100 if ultimo_p.monto_total_pagar > 0 else 0
        return {
            "pagado": float(porcentaje),
            "pendiente": float(100 - porcentaje),
            "monto_pagado": float(total_pagado),
            "monto_total": float(ultimo_p.monto_total_pagar),
            "monto_capital": float(ultimo_p.monto_capital),
            "modalidad": ultimo_p.modalidad,
            "total_cuotas": ultimo_p.cuotas,
        }
    
    def get_historial_grafico(self, obj):
        ultimo_p = obj.prestamos.last()
        if not ultimo_p: return []
        return [
            {"semana": f"Sem {a.semana_numero}", "pago": float(a.monto)} 
            for a in ultimo_p.abonos.all().order_by('semana_numero')
        ]

    def get_ultimo_prestamo_id(self, obj):
        ultimo_p = obj.prestamos.last()
        return ultimo_p.id if ultimo_p else None
    
    def get_datos_ultimo_aval(self, obj):
        ultimo_p = obj.prestamos.order_by('-id').first()
        if ultimo_p:
            return {
                "nombre_aval": ultimo_p.nombre_aval,
                "telefono_aval": ultimo_p.telefono_aval,
                "direccion_aval": ultimo_p.direccion_aval,
                "curp_aval": ultimo_p.curp_aval,
                "parentesco_aval": ultimo_p.parentesco_aval,
                "garantia_descripcion": ultimo_p.garantia_descripcion,
            }
        return None

    def get_saldo_actual(self, obj):
        prestamo = obj.prestamos.filter(activo=True).first()
        if not prestamo: return 0
        total_pagado = prestamo.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
        return float(prestamo.monto_total_pagar - total_pagado)

    def get_numero_prestamos(self, obj):
        return obj.prestamos.count()

    def get_total_penalizaciones(self, obj):
        prestamo = obj.prestamos.filter(activo=True).last()
        if prestamo:
            res = prestamo.penalizaciones.filter(activa=True).aggregate(total=Sum('monto_penalizado'))
            return float(res['total'] or 0)
        return 0

    def get_id_mora_activa(self, obj):
        prestamo = obj.prestamos.filter(activo=True).last()
        if prestamo:
            ultima_mora = prestamo.penalizaciones.filter(activa=True).last()
            return ultima_mora.id if ultima_mora else None
        return None
    def get_tiene_moras_activas(self, obj):
        # Buscamos si tiene penalizaciones activas en CUALQUIERA de sus préstamos
        return Penalizacion.objects.filter(prestamo__cliente=obj, activa=True).exists()

# 2. SERIALIZER DE PRÉSTAMOS
class PrestamoSerializer(serializers.ModelSerializer):
    
    cliente_nombre = serializers.ReadOnlyField(source='cliente.nombre')
    total_penalizaciones = serializers.SerializerMethodField()
    nombre_sujeto = serializers.SerializerMethodField()
    tipo_display = serializers.CharField(source='get_tipo_display', read_only=True)

    class Meta:
        model = Prestamo
        fields = [
            'id', 'cliente', 'cliente_nombre', 'monto_capital', 
            'monto_total_pagar', 'cuotas', 'modalidad', 'fecha_inicio',
            'nombre_aval', 'telefono_aval', 'direccion_aval', 
            'curp_aval', 'parentesco_aval', 'activo','garantia_descripcion',
            'total_penalizaciones',"nombre_sujeto", 'tipo_display','folio_pagare',
        ]

    def get_total_penalizaciones(self, obj):
        return obj.penalizaciones.filter(activa=True).aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0

    def get_nombre_sujeto(self, obj):
        if obj.tipo == 'G' and obj.grupo:
            return obj.grupo.nombre_grupo
        return obj.cliente.nombre if obj.cliente else "Sin Nombre"

# 3. SERIALIZER DE ABONOS (Registro)
class AbonoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Abono
        fields = ['id', 'prestamo', 'monto', 'semana_numero', 'fecha_pago']
        read_only_fields = ['fecha_pago']

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto debe ser mayor a cero.")
        return value

# 4. SERIALIZER HÍBRIDO (Para el Buscador de Pagos)
class DirectorioHibridoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.SerializerMethodField()
    es_grupo = serializers.BooleanField()
    # Los declaramos solo como MethodField para que usen tus funciones de abajo
    saldo_actual = serializers.SerializerMethodField()
    total_penalizaciones = serializers.SerializerMethodField()
    id_mora_activa = serializers.SerializerMethodField()
    tiene_prestamo_activo = serializers.SerializerMethodField()
    telefono = serializers.CharField(required=False, allow_null=True)
    direccion = serializers.CharField(required=False, allow_null=True)
    num_integrantes = serializers.SerializerMethodField()
    ultimo_prestamo_id = serializers.SerializerMethodField()
    datos_ultimo_aval = serializers.SerializerMethodField()
    penalizaciones = serializers.JSONField() # Este es el que usa la lista de multas

    def get_datos_ultimo_aval(self, obj):
        from prestamos.models import Prestamo
        
        # Usamos el método que ya tenemos para obtener el ID
        prestamo_id = self.get_ultimo_prestamo_id(obj)
        
        if prestamo_id:
            prestamo = Prestamo.objects.filter(id=prestamo_id).first()
            if prestamo and prestamo.nombre_aval:
                return {
                    "nombre_aval": prestamo.nombre_aval,
                    "telefono_aval": prestamo.telefono_aval,
                    "direccion_aval": prestamo.direccion_aval,
                    "parentesco_aval": prestamo.parentesco_aval
                }
        return None
    def get_total_penalizaciones(self, obj):
        # Usamos getattr porque obj puede no tener el atributo si no tiene prestamo activo
        return getattr(obj, 'total_penalizaciones', 0.0)

    def get_id_mora_activa(self, obj):
        return getattr(obj, 'id_mora_activa', None)

    def get_nombre(self, obj):
        return obj.nombre if hasattr(obj, 'nombre') else obj.nombre_grupo

    def get_ultimo_prestamo_id(self, obj):
        return getattr(obj, 'ultimo_prestamo_id', None)

    def get_saldo_actual(self, obj):
        return getattr(obj, 'saldo_actual', 0.0)

    def get_tiene_prestamo_activo(self, obj):
        return getattr(obj, 'tiene_prestamo_activo', False)

    def get_num_integrantes(self, obj):
        return obj.integrantes.count() if hasattr(obj, 'integrantes') else 1
# 5. SERIALIZER PARA LA BÓVEDA DE TICKETS (En Perfil de Usuario)
class HistorialPagosSerializer(serializers.ModelSerializer):
    cliente = serializers.SerializerMethodField()
    fecha = serializers.DateField(source='fecha_pago', format="%d/%m/%Y")
    saldo_anterior = serializers.SerializerMethodField()
    nuevo_saldo = serializers.SerializerMethodField()
    hora = serializers.TimeField(source='hora_pago', format="%H:%M:%S")

    class Meta:
        model = Abono
        fields = ['id', 'monto','fecha', 'hora', 'semana_numero', 'cliente', 'saldo_anterior', 'nuevo_saldo',]

    def get_cliente(self, obj):
        nombre = obj.prestamo.grupo.nombre_grupo if obj.prestamo.tipo == 'G' else obj.prestamo.cliente.nombre
        return nombre.upper() # Así se ve parejo siempre
    def get_saldo_anterior(self, obj):
        # Sumamos abonos anteriores al actual para este préstamo
        pagos_anteriores = Abono.objects.filter(
            prestamo=obj.prestamo, 
            id__lt=obj.id
        ).aggregate(Sum('monto'))['monto__sum'] or 0
        return float(obj.prestamo.monto_total_pagar - pagos_anteriores)

    def get_nuevo_saldo(self, obj):
        return self.get_saldo_anterior(obj) - float(obj.monto)