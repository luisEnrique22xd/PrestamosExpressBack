from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal
import pytz

class Command(BaseCommand):
    help = 'Aplica penalización del 1.5% diario basado en la zona horaria de México'

    def handle(self, *args, **options):
        # 1. Forzar que 'hoy' sea la fecha real en México
        mexico_tz = pytz.timezone('America/Mexico_City')
        hoy = timezone.now().astimezone(mexico_tz).date()
        
        self.stdout.write(f"Iniciando proceso de moras para fecha local: {hoy}")

        # 2. Filtramos préstamos activos
        prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
        conteo_aplicados = 0

        for p in prestamos_activos:
            # Pasar la zona horaria al verificador
            tiene_atraso = self.verificar_atraso_real(p, hoy, mexico_tz)

            if tiene_atraso:
                # Evitar duplicados para el mismo día calendario en México
                ya_aplicado = Penalizacion.objects.filter(
                    prestamo=p, 
                    fecha_aplicacion=hoy 
                ).exists()

                if not ya_aplicado:
                    monto_base = p.monto_capital 
                    monto_mora = monto_base * Decimal('0.015')
                    
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        activa=True,
                        descripcion=f"Recargo automático 1.5% - Día {hoy}",
                        fecha_aplicacion=hoy
                    )
                    
                    conteo_aplicados += 1
                    self.stdout.write(self.style.SUCCESS(f"Mora de ${monto_mora} aplicada a: {p.cliente if p.cliente else p.grupo}"))

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

    def verificar_atraso_real(self, p, hoy, tz):
        # Convertimos la fecha de inicio (que está en UTC/Indonesia) a México
        fecha_base = p.fecha_inicio.astimezone(tz).date()

        for i in range(1, p.cuotas + 1):
            if p.modalidad in ["Semanal", "S"]:
                fv = fecha_base + timedelta(days=7 * i)
            elif p.modalidad in ["Quincenal", "Q"]:
                fv = fecha_base + timedelta(days=15 * i)
            elif p.modalidad in ["Mensual", "M"]:
                fv = fecha_base + timedelta(days=30 * i)
            else:
                fv = fecha_base + timedelta(days=7 * i)

            if fv.weekday() == 6: # Domingo -> Lunes
                fv += timedelta(days=1)

            # Usamos < para que el comando no cobre el mismo día del vencimiento
            # (Le damos a la gente hasta las 11:59 PM para pagar)
            if fv < hoy:
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True 
        return False