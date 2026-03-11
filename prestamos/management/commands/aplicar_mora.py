from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta

class Command(BaseCommand):
    help = 'Aplica una penalización del 1.5% diario a préstamos con cuotas vencidas'

    def handle(self, *args, **options):
        hoy = timezone.now().date()
        # Solo préstamos que estén marcados como activos
        prestamos_activos = Prestamo.objects.filter(activo=True)
        conteo_aplicados = 0

        for p in prestamos_activos:
            # Lógica: ¿Tiene abonos pendientes cuya fecha programada ya pasó?
            # Buscamos en tus proyecciones (si las guardas en DB) o calculamos
            # Aquí asumimos que verificas si el saldo pendiente es mayor a 0 y hay atraso
           if hoy > cuota.fecha_vencimiento and not cuota.pagado:
        # Aquí calculamos el 1.5% diario
       
            # 1. Calculamos el monto de la mora (1.5% del capital inicial)
            monto_mora = float(p.monto_capital) * 0.015
            
            # 2. Verificamos si hoy ya se aplicó (para no duplicar si se corre el comando 2 veces)
            ya_aplicado = Penalizacion.objects.filter(prestamo=p, fecha_aplicacion=hoy).exists()

            if not ya_aplicado:
                # Solo aplicamos si hay evidencia de atraso (ejemplo: fecha_inicio + cuotas < hoy)
                # Esta validación la puedes ajustar según cómo guardes las fechas de abono
                Penalizacion.objects.create(
                    prestamo=p,
                    monto_penalizado=monto_mora,
                    descripcion=f"Recargo automático 1.5% - Día {hoy}"
                )
                
                # Actualizamos el monto total a pagar en el préstamo
                p.monto_total_pagar = float(p.monto_total_pagar) + monto_mora
                p.save()
                conteo_aplicados += 1

        self.stdout.write(self.style.SUCCESS(f'Se aplicaron {conteo_aplicados} penalizaciones hoy {hoy}'))