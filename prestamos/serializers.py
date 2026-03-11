from rest_framework import serializers
from .models import Cliente, Prestamo,Abono
from prestamos import models

# Este es el que te falta según el error
class ClienteSerializer(serializers.ModelSerializer):
    tiene_prestamo_activo = serializers.SerializerMethodField()
    datos_ultimo_aval = serializers.SerializerMethodField()
    progreso_pagos = serializers.SerializerMethodField()
    historial_grafico = serializers.SerializerMethodField()
    ultimo_prestamo_id = serializers.SerializerMethodField()
    saldo_actual = serializers.SerializerMethodField()
    class Meta:
        model = Cliente
        fields = ['id', 'nombre', 'telefono', 'curp', 'direccion','fecha_nacimiento', 'datos_ultimo_aval','progreso_pagos', 'historial_grafico', 'ultimo_prestamo_id','tiene_prestamo_activo','saldo_actual',  ]
    def get_tiene_prestamo_activo(self, obj):
    # Buscamos el préstamo que dice estar activo
        prestamo = obj.prestamos.filter(activo=True).first()
    
        if prestamo:
        # Calculamos el saldo real en este momento
            total_pagado = sum(abono.monto for abono in prestamo.abonos.all())
        
        # SI YA PAGÓ TODO: Lo desactivamos de una vez (Auto-liquidación)
            if total_pagado >= prestamo.monto_total_pagar:
                prestamo.activo = False
                prestamo.save()
                return False # Ya no está activo
            
            return True # Sigue debiendo
        return False
    
    def get_progreso_pagos(self, obj):
        ultimo_p = Prestamo.objects.filter(cliente=obj).last()
        if not ultimo_p: return {"pagado": 0, "pendiente": 100}
        
        total_pagado = sum(a.monto for a in ultimo_p.abonos.all())
        porcentaje = (total_pagado / ultimo_p.monto_total_pagar) * 100
        return {
            "pagado": float(porcentaje),
            "pendiente": float(100 - porcentaje),
            "monto_pagado": float(total_pagado),
            "monto_total": float(ultimo_p.monto_total_pagar),
            "monto_capital": float(ultimo_p.monto_capital)
            
        }
    
    def get_historial_grafico(self, obj):
        ultimo_p = Prestamo.objects.filter(cliente=obj).last()
        if not ultimo_p: return []
        
        # Formateamos los datos exactamente como los pide Recharts
        return [
            {"semana": f"Sem {a.semana_numero}", "pago": float(a.monto)} 
            for a in ultimo_p.abonos.all().order_by('semana_numero')
        ]
    def get_ultimo_prestamo_id(self, obj):
        ultimo_p = Prestamo.objects.filter(cliente=obj).last()
        return ultimo_p.id if ultimo_p else None
    
    
    def get_datos_ultimo_aval(self, obj):
        # Buscamos en la tabla de Préstamos el registro más reciente para este cliente
        ultimo_p = Prestamo.objects.filter(cliente=obj).order_by('-id').first()
        
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
        # Saldo = (Monto Total + Penalizaciones) - Abonos Realizados
        prestamo = obj.prestamos.filter(activo=True).first()
        if not prestamo:
            return 0
        
        # Django suma automáticamente las penalizaciones al monto_total_pagar en el comando anterior
        # Así que solo restamos lo que ya pagó
        total_pagado = sum(a.monto for a in prestamo.abonos.all())
        return float(prestamo.monto_total_pagar) - float(total_pagado)

# Este es el que agregamos para los préstamos
class PrestamoSerializer(serializers.ModelSerializer):
    cliente_nombre = serializers.ReadOnlyField(source='cliente.nombre')
    total_penalizaciones = serializers.SerializerMethodField()
    class Meta:
        model = Prestamo
        fields = [
            'id', 'cliente', 'cliente_nombre', 'monto_capital', 
            'monto_total_pagar', 'cuotas', 'modalidad', 'fecha_inicio',
            'nombre_aval', 'telefono_aval', 'direccion_aval', 
            'curp_aval', 'parentesco_aval', 'activo','garantia_descripcion','total_penalizaciones'
        ]
    def get_total_penalizaciones(self, obj):
        # Sumamos solo las penalizaciones que están "activas" (no condonadas)
        from django.db.models import Sum
        return obj.penalizaciones.filter(activa=True).aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0
        

class AbonoSerializer(serializers.ModelSerializer):
    class Meta:
        model = Abono
        fields = ['id', 'prestamo', 'monto', 'semana_numero', 'fecha_pago']
        read_only_fields = ['fecha_pago']

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("El monto del abono debe ser mayor a cero.")
        return value

    def create(self, validated_data):
        # Aquí puedes agregar lógica extra, como verificar que el abono 
        # no exceda el saldo pendiente del préstamo.
        return super().create(validated_data)
    
