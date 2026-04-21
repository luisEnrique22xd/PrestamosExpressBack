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
    # 🔥 Agregamos el campo que necesita el Front para las tarjetas
    prestamos_activos = serializers.SerializerMethodField()

    class Meta:
        model = Cliente
        fields = [
            'id', 'nombre', 'telefono', 'curp', 'direccion','fecha_nacimiento', 
            'datos_ultimo_aval','progreso_pagos', 'historial_grafico', 
            'ultimo_prestamo_id','tiene_prestamo_activo','saldo_actual',
            'numero_prestamos','total_penalizaciones', 'id_mora_activa',
            'tiene_moras_activas', 'prestamos_activos'
        ]

    def get_prestamos_activos(self, obj):
        # Usamos related_name 'prestamos'
        qs = obj.prestamos.filter(activo=True).order_by('-fecha_creacion')
        return [{
            "id": p.id,
            "folio": p.folio_pagare or 0,
            "monto_total": float(p.monto_total_pagar),
            "capital": float(p.monto_capital),
            "cuotas": p.cuotas,
            "modalidad": p.get_modalidad_display(),
            "aval": p.nombre_aval
        } for p in qs]

    def get_saldo_actual(self, obj):
        from django.db.models import Sum
        # Calculamos la deuda real sumando saldo de cada préstamo activo
        total_global = 0
        prestamos = obj.prestamos.filter(activo=True)
        
        for p in prestamos:
            # Suma de abonos de este préstamo
            pagado = p.abonos.aggregate(total=Sum('monto'))['total'] or 0
            # Suma de multas activas de este préstamo
            multas = p.penalizaciones.filter(activa=True).aggregate(total=Sum('monto_penalizado'))['total'] or 0
            
            saldo_p = (float(p.monto_total_pagar) - float(pagado)) + float(multas)
            total_global += saldo_p
            
        return total_global

    def get_tiene_prestamo_activo(self, obj):
        return obj.prestamos.filter(activo=True).exists()

    def get_ultimo_prestamo_id(self, obj):
        ultimo = obj.prestamos.filter(activo=True).last()
        return ultimo.id if ultimo else None

    def get_progreso_pagos(self, obj):
        # Mantenemos la lógica para el gráfico superior basada en el último
        ultimo_p = obj.prestamos.filter(activo=True).last()
        if not ultimo_p: return {"pagado": 0, "pendiente": 100}
        from django.db.models import Sum
        total_pagado = ultimo_p.abonos.aggregate(total=Sum('monto'))['total'] or 0
        porcentaje = (float(total_pagado) / float(ultimo_p.monto_total_pagar)) * 100 if ultimo_p.monto_total_pagar > 0 else 0
        return {
            "pagado": round(porcentaje, 2),
            "monto_pagado": float(total_pagado),
            "monto_total": float(ultimo_p.monto_total_pagar),
            "monto_capital": float(ultimo_p.monto_capital),
            "modalidad": ultimo_p.modalidad,
            "total_cuotas": ultimo_p.cuotas,
        }

    def get_historial_grafico(self, obj):
        ultimo_p = obj.prestamos.filter(activo=True).last()
        if not ultimo_p: return []
        return [{"semana": f"Sem {a.semana_numero}", "pago": float(a.monto)} 
                for a in ultimo_p.abonos.all().order_by('semana_numero')]

    def get_datos_ultimo_aval(self, obj):
        p = obj.prestamos.filter(activo=True).last()
        if p:
            return {
                "nombre_aval": p.nombre_aval,
                "telefono_aval": p.telefono_aval,
                "direccion_aval": p.direccion_aval,
                "curp_aval": p.curp_aval,
                "parentesco_aval": p.parentesco_aval,
                "garantia_descripcion": p.garantia_descripcion,
            }
        return None

    def get_numero_prestamos(self, obj):
        return obj.prestamos.count()

    def get_total_penalizaciones(self, obj):
        from django.db.models import Sum
        res = obj.prestamos.filter(activo=True).aggregate(total=Sum('penalizaciones__monto_penalizado'))
        return float(res['total'] or 0)

    def get_id_mora_activa(self, obj):
        p = obj.prestamos.filter(activo=True).last()
        if p:
            ultima = p.penalizaciones.filter(activa=True).last()
            return ultima.id if ultima else None
        return None

    def get_tiene_moras_activas(self, obj):
        return obj.prestamos.filter(activo=True, penalizaciones__activa=True).exists()
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
            'nombre_aval', 'telefono_aval', 'direccion_aval','nombre_aval_2', 'telefono_aval_2', 'direccion_aval_2', 'curp_aval_2', 'parentesco_aval_2', 
            'curp_aval', 'parentesco_aval', 'activo','garantia_descripcion',
            'total_penalizaciones',"nombre_sujeto", 'tipo_display','folio_pagare',
        ]
    def validate(self, data):
        """
        Validación: Si el préstamo supera los $7,500, el segundo aval es obligatorio.
        """
        monto = data.get('monto_capital')
        cliente = data.get('cliente')
        # Extraemos la bandera de urgencia que enviaremos desde el Front
        es_urgente = self.context.get('request').data.get('es_urgente', False)
        
        # 1. VALIDACIÓN DE DEUDA PREVIA (Solo si no es urgente)
        if cliente and not es_urgente:
            # Asumiendo que tu modelo Cliente tiene saldo_actual o un método similar
            if cliente.saldo_actual > 0:
                raise serializers.ValidationError({
                    "error": f"El cliente {cliente.nombre} tiene una deuda activa de ${cliente.saldo_actual}. Active el modo urgente para permitir un segundo préstamo."
                })
        
        
        # 2. VALIDACIÓN DE SEGUNDO AVAL (Esta se queda igual)
        if monto and monto > 7500:
            # Verificamos que los campos esenciales del segundo aval no estén vacíos
            if not data.get('nombre_aval_2') or not data.get('curp_aval_2'):
                raise serializers.ValidationError({
                    "nombre_aval_2": "Para préstamos mayores a $7,500 es obligatorio registrar un segundo aval con nombre y CURP."
                })
        return data
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

class DirectorioHibridoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    nombre = serializers.SerializerMethodField()
    es_grupo = serializers.BooleanField()
    curp = serializers.CharField(required=False, allow_null=True)
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)
    saldo_actual = serializers.SerializerMethodField()
    total_penalizaciones = serializers.SerializerMethodField()
    id_mora_activa = serializers.SerializerMethodField()
    tiene_prestamo_activo = serializers.SerializerMethodField()
    telefono = serializers.CharField(required=False, allow_null=True)
    direccion = serializers.CharField(required=False, allow_null=True)
    num_integrantes = serializers.SerializerMethodField()
    ultimo_prestamo_id = serializers.SerializerMethodField()
    datos_ultimo_aval = serializers.SerializerMethodField()
    penalizaciones = serializers.JSONField()
    
    # Campo para la lista de deudas separadas
    prestamos_activos = serializers.SerializerMethodField()

    def get_prestamos_activos(self, obj):
        # Accedemos a los préstamos a través del related_name 'prestamos' definido en tu modelo
        if hasattr(obj, 'prestamos'):
            # Filtramos solo los activos
            qs = obj.prestamos.filter(activo=True).order_by('-fecha_creacion')
            return [{
                "id": p.id,
                "folio": p.folio_pagare,
                "monto_total": float(p.monto_total_pagar),
                "capital": float(p.monto_capital),
                "modalidad": p.get_modalidad_display(),
                "aval": p.nombre_aval
            } for p in qs]
        return []

    def get_nombre(self, obj):
        return obj.nombre if hasattr(obj, 'nombre') else obj.nombre_grupo

    def get_saldo_actual(self, obj):
        return getattr(obj, 'saldo_actual', 0.0)

    def get_total_penalizaciones(self, obj):
        return getattr(obj, 'total_penalizaciones', 0.0)

    def get_id_mora_activa(self, obj):
        return getattr(obj, 'id_mora_activa', None)

    def get_tiene_prestamo_activo(self, obj):
        return getattr(obj, 'tiene_prestamo_activo', False)

    def get_ultimo_prestamo_id(self, obj):
        # Intentamos obtener el ID del último préstamo activo de forma segura
        if hasattr(obj, 'prestamos'):
            last_p = obj.prestamos.filter(activo=True).last()
            return last_p.id if last_p else None
        return None

    def get_num_integrantes(self, obj):
        return obj.integrantes.count() if hasattr(obj, 'integrantes') else 1

    def get_datos_ultimo_aval(self, obj):
        if hasattr(obj, 'prestamos'):
            p = obj.prestamos.filter(activo=True).last()
            if p:
                return {
                    "nombre_aval": p.nombre_aval,
                    "telefono_aval": p.telefono_aval,
                    "direccion_aval": p.direccion_aval,
                    "parentesco_aval": p.parentesco_aval
                }
        return None
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
        # Saldo de capital justo antes de este abono
        pagos_anteriores = Abono.objects.filter(
            prestamo=obj.prestamo, 
            id__lt=obj.id
        ).aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
        return float(obj.prestamo.monto_total_pagar - pagos_anteriores)

    def get_nuevo_saldo(self, obj):
        # Simplemente restamos el abono actual al saldo anterior de capital
        return self.get_saldo_anterior(obj) - float(obj.monto)