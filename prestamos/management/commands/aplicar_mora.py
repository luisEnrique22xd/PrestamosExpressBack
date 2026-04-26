from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal
import pytz

class Command(BaseCommand):
    help = 'Aplica penalización diaria del 1% (incluye domingos) en todas las modalidades'

    def handle(self, *args, **options):
        # 1. Forzar fecha real en México
        mexico_tz = pytz.timezone('America/Mexico_City')
        hoy = timezone.now().astimezone(mexico_tz).date()
        
        self.stdout.write(f"Iniciando proceso de moras global para fecha local: {hoy}")

        # 2. Filtramos todos los préstamos activos
        prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
        conteo_aplicados = 0

        for p in prestamos_activos:
            # Verificamos si tiene atraso real
            tiene_atraso = self.verificar_atraso_real(p, hoy, mexico_tz)

            if tiene_atraso:
                # Evitar duplicados para el mismo día calendario
                ya_aplicado = Penalizacion.objects.filter(
                    prestamo=p, 
                    fecha_aplicacion=hoy 
                ).exists()

                if not ya_aplicado:
                    # 1% del capital original
                    monto_mora = p.monto_capital * Decimal('0.01')
                    
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        activa=True,
                        descripcion=f"Recargo automático 1% - Corte {hoy}",
                        fecha_aplicacion=hoy
                    )
                    
                    conteo_aplicados += 1
                    # Identificar si es cliente individual o grupo para el log
                    sujeto = p.cliente.nombre if p.cliente else p.grupo.nombre_grupo
                    self.stdout.write(self.style.SUCCESS(f"Mora de ${monto_mora} aplicada a: {sujeto}"))

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

    def verificar_atraso_real(self, p, hoy, tz):
        # Convertimos la fecha de inicio a la zona horaria de México
        fecha_base = p.fecha_inicio.astimezone(tz).date()

        for i in range(1, p.cuotas + 1):
            # Calculamos fv (fecha vencimiento) según modalidad
            if p.modalidad in ["Semanal", "S"]:
                fv = fecha_base + timedelta(days=7 * i)
            elif p.modalidad in ["Quincenal", "Q"]:
                fv = fecha_base + timedelta(days=15 * i)
            elif p.modalidad in ["Mensual", "M"]:
                fv = fecha_base + timedelta(days=30 * i)
            else:
                fv = fecha_base + timedelta(days=7 * i)

            # 🔥 REGLA GLOBAL: NO HAY SALTOS DE DOMINGO.
            # Si el vencimiento (fv) es menor que hoy, ya es mora.
            if fv < hoy:
                # Si no existe el abono para esta cuota específica, hay atraso
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True 
                    
        return False