from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Aplica una penalización del 1.5% diario sobre el monto_capital a préstamos vencidos'

    def handle(self, *args, **options):
        # Fecha local de México
        hoy = timezone.localtime(timezone.now()).date()
        
        # Filtramos préstamos activos
        prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
        conteo_aplicados = 0

        for p in prestamos_activos:
            # Verificar si tiene atraso real (basado en fechas de cuotas)
            tiene_atraso = self.verificar_atraso_real(p, hoy)

            if tiene_atraso:
                # Evitar duplicados: Revisa si ya se aplicó mora el día de HOY
                self.stdout.write(f"ATRASO DETECTADO en préstamo {p.id} ({p.cliente})")
                ya_aplicado = Penalizacion.objects.filter(
                    prestamo=p, 
                    fecha_aplicacion=hoy 
                ).exists()

                if not ya_aplicado:
                    # Cálculo del 1.5% sobre monto_capital (Capital puro)
                    monto_base = p.monto_capital 
                    monto_mora = monto_base * Decimal('0.015')
                    
                    # Crear el registro de penalización
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        activa=True,
                        descripcion=f"Recargo automático 1.5% - Día {hoy}",
                        fecha_aplicacion=hoy
                    )
                    
                    # Actualizar el saldo total acumulado para el cobro
                    p.monto_total_pagar += monto_mora
                    p.save()
                    
                    conteo_aplicados += 1
                    self.stdout.write(f"Mora de ${monto_mora} aplicada a: {p.cliente if p.cliente else p.grupo}")

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

    def verificar_atraso_real(self, p, hoy):
        fecha_base = p.fecha_inicio
        if hasattr(fecha_base, 'date'):
            fecha_base = fecha_base.date()

        for i in range(1, p.cuotas + 1):
            # Lógica de fechas según modalidad
            if p.modalidad in ["Semanal", "S"]:
                fecha_pago = fecha_base + timedelta(days=7 * i)
            elif p.modalidad in ["Quincenal", "Q"]:
                fecha_pago = fecha_base + timedelta(days=15 * i)
            elif p.modalidad in ["Mensual", "M"]:
                fecha_pago = fecha_base + timedelta(days=30 * i)
            else:
                fecha_pago = fecha_base + timedelta(days=7 * i)

            if fecha_pago.weekday() == 6: # Domingo -> Lunes
                fecha_pago += timedelta(days=1)

            # Si la fecha de pago ya pasó y no hay abono registrado
            if fecha_pago < hoy:
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True 
        return False