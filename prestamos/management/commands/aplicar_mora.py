# from django.core.management.base import BaseCommand
# from django.utils import timezone
# from prestamos.models import Prestamo, Penalizacion
# from datetime import timedelta
# from decimal import Decimal
# import pytz

# class Command(BaseCommand):
#     help = 'Aplica penalización del 1% diario basado en la zona horaria de México'

#     def handle(self, *args, **options):
#         # 1. Forzar que 'hoy' sea la fecha real en México
#         mexico_tz = pytz.timezone('America/Mexico_City')
#         hoy = timezone.now().astimezone(mexico_tz).date()
        
#         self.stdout.write(f"Iniciando proceso de moras para fecha local: {hoy}")

#         # 2. Filtramos préstamos activos
#         prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
#         conteo_aplicados = 0

#         for p in prestamos_activos:
#             # Pasar la zona horaria al verificador
#             tiene_atraso = self.verificar_atraso_real(p, hoy, mexico_tz)

#             if tiene_atraso:
#                 # Evitar duplicados para el mismo día calendario en México
#                 ya_aplicado = Penalizacion.objects.filter(
#                     prestamo=p, 
#                     fecha_aplicacion=hoy 
#                 ).exists()

#                 if not ya_aplicado:
#                     monto_base = p.monto_capital 
#                     monto_mora = monto_base * Decimal('0.01')
                    
#                     Penalizacion.objects.create(
#                         prestamo=p,
#                         monto_penalizado=monto_mora,
#                         activa=True,
#                         descripcion=f"Recargo automático 1% - Día {hoy}",
#                         fecha_aplicacion=hoy
#                     )
                    
#                     conteo_aplicados += 1
#                     self.stdout.write(self.style.SUCCESS(f"Mora de ${monto_mora} aplicada a: {p.cliente if p.cliente else p.grupo}"))

#         self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

#     def verificar_atraso_real(self, p, hoy, tz):
#         # Convertimos la fecha de inicio (que está en UTC/Indonesia) a México
#         fecha_base = p.fecha_inicio.astimezone(tz).date()

#         for i in range(1, p.cuotas + 1):
#             if p.modalidad in ["Semanal", "S"]:
#                 fv = fecha_base + timedelta(days=7 * i)
#             elif p.modalidad in ["Quincenal", "Q"]:
#                 fv = fecha_base + timedelta(days=15 * i)
#             elif p.modalidad in ["Mensual", "M"]:
#                 fv = fecha_base + timedelta(days=30 * i)
#             else:
#                 fv = fecha_base + timedelta(days=7 * i)

#             if fv.weekday() == 6: # Domingo -> Lunes
#                 fv += timedelta(days=1)

#             # Usamos < para que el comando no cobre el mismo día del vencimiento
#             # (Le damos a la gente hasta las 11:59 PM para pagar)
#             if fv < hoy:
#                 pagado = p.abonos.filter(semana_numero=i).exists()
#                 if not pagado:
#                     return True 
#         return False

from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal
import pytz

class Command(BaseCommand):
    help = 'Aplica penalización del 1% diario con reglas diferenciadas por modalidad'

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
                    monto_mora = monto_base * Decimal('0.01')
                    
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        activa=True,
                        descripcion=f"Recargo automático 1% - Corte {hoy}",
                        fecha_aplicacion=hoy
                    )
                    
                    conteo_aplicados += 1
                    sujeto = p.cliente.nombre if p.cliente else p.grupo.nombre_grupo
                    self.stdout.write(self.style.SUCCESS(f"Mora de ${monto_mora} aplicada a: {sujeto}"))

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas.'))

    def verificar_atraso_real(self, p, hoy, tz):
        # Convertimos la fecha de inicio a la zona horaria de México
        fecha_base = p.fecha_inicio.astimezone(tz).date()

        for i in range(1, p.cuotas + 1):
            # 1. Calculamos la fecha de vencimiento teórica (fv)
            if p.modalidad in ["Semanal", "S"]:
                fv = fecha_base + timedelta(days=7 * i)
                # 🚀 REGLA SEMANAL: No hay salto de domingo. 
                # Si fv es Sábado y hoy es Domingo -> YA HAY MORA.
            
            elif p.modalidad in ["Quincenal", "Q"]:
                fv = fecha_base + timedelta(days=15 * i)
                # 🕊️ REGLA QUINCENAL: Domingo de gracia.
                if fv.weekday() == 5: # Si el vencimiento es Sábado
                    fv += timedelta(days=1) # Se mueve al Domingo para que la mora inicie el Lunes
            
            elif p.modalidad in ["Mensual", "M"]:
                fv = fecha_base + timedelta(days=30 * i)
                # 🕊️ REGLA MENSUAL: Domingo de gracia.
                if fv.weekday() == 5: 
                    fv += timedelta(days=1)
            else:
                fv = fecha_base + timedelta(days=7 * i)

            # 2. Verificamos si fv ya pasó (FV < HOY)
            if fv < hoy:
                # 3. Verificamos si esa cuota específica no ha sido pagada
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True 
                    
        return False