from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Aplica una penalización del 1.5% diario sobre el capital inicial a préstamos vencidos'

    def handle(self, *args, **options):
        # Usamos la fecha local de México para la comparación
        hoy = timezone.localtime(timezone.now()).date()
        
        # 1. Filtramos préstamos activos y precargamos abonos para velocidad
        prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
        conteo_aplicados = 0

        for p in prestamos_activos:
            # 2. Verificar si tiene al menos una cuota vencida sin abono
            tiene_atraso = self.verificar_atraso_real(p, hoy)

            if tiene_atraso:
                # 3. Evitar duplicados: ¿Ya se le aplicó mora hoy?
                # Nota: El campo en tu modelo se llama 'fecha_penalizacion' según errores previos
                # Si no existe, Django usará el auto_now_add si lo tienes configurado.
                ya_aplicado = Penalizacion.objects.filter(
                    prestamo=p, 
                    fecha_penalizacion__date=hoy 
                ).exists()

                if not ya_aplicado:
                    # 4. Cálculo del 1.5% sobre el CAPITAL INICIAL (campo 'monto')
                    # Si el campo se llama 'monto_prestado', cámbialo aquí:
                    monto_base = p.monto 
                    monto_mora = monto_base * Decimal('0.015')
                    
                    # 5. Crear el registro de penalización
                    # Quitamos 'motivo' y 'descripcion' para evitar el TypeError previo
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        activa=True
                    )
                    
                    # 6. Actualizar el saldo total del préstamo para que Alexander vea el cobro
                    p.monto_total_pagar += monto_mora
                    p.save()
                    
                    conteo_aplicados += 1
                    self.stdout.write(f"Mora de ${monto_mora} aplicada a: {p.cliente}")

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

    def verificar_atraso_real(self, p, hoy):
        """
        Calcula las fechas de pago y revisa si alguna ya pasó y no tiene abono.
        """
        # Limpiamos la fecha de inicio de horas para comparar solo días
        fecha_base = p.fecha_inicio
        if hasattr(fecha_base, 'date'):
            fecha_base = fecha_base.date()

        for i in range(1, p.cuotas + 1):
            # 7. Cálculo de fecha según modalidad (S, Q, M)
            if p.modalidad in ["Semanal", "S"]:
                fecha_pago = fecha_base + timedelta(days=7 * i)
            elif p.modalidad in ["Quincenal", "Q"]:
                fecha_pago = fecha_base + timedelta(days=15 * i)
            elif p.modalidad in ["Mensual", "M"]:
                fecha_pago = fecha_base + timedelta(days=30 * i)
            else:
                fecha_pago = fecha_base + timedelta(days=7 * i)

            # Regla de domingos: Si el cobro caía en domingo, se revisa a partir del lunes
            if fecha_pago.weekday() == 6:
                fecha_pago += timedelta(days=1)

            # Si la fecha de pago ya pasó (ayer o antes)
            if fecha_pago < hoy:
                # 8. Revisamos si existe el abono para esa cuota específica
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True # Hay al menos una cuota vieja sin pagar
        
        return False