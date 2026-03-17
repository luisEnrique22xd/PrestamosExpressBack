from django.core.management.base import BaseCommand
from django.utils import timezone
from prestamos.models import Prestamo, Penalizacion
from datetime import timedelta
from decimal import Decimal

class Command(BaseCommand):
    help = 'Aplica una penalización del 1.5% diario a préstamos con cuotas vencidas'

    def handle(self, *args, **options):
        hoy = timezone.now().date()
        # 1. Filtramos solo préstamos activos
        prestamos_activos = Prestamo.objects.filter(activo=True).prefetch_related('abonos')
        conteo_aplicados = 0

        for p in prestamos_activos:
            # 2. Verificar si tiene al menos una cuota vencida sin abono
            tiene_atraso = self.verificar_atraso_real(p, hoy)

            if tiene_atraso:
                # 3. Evitar duplicados: ¿Ya se le aplicó mora hoy?
                ya_aplicado = Penalizacion.objects.filter(
                    prestamo=p, 
                    fecha_aplicacion=hoy 
                ).exists()

                if not ya_aplicado:
                    # 4. Cálculo del 1.5% sobre el MONTO CAPITAL
                    monto_mora = p.monto_capital * Decimal('0.015')
                    
                    # 5. Crear el registro de penalización con los campos reales
                    Penalizacion.objects.create(
                        prestamo=p,
                        monto_penalizado=monto_mora,
                        descripcion=f"Recargo automático 1.5% - Día {hoy}",
                        activa=True,
                        fecha_aplicacion=hoy
                    )
                    
                    # 6. Actualizar el saldo total del préstamo
                    # Usamos monto_total_pagar que confirmamos que existe en tu modelo
                    p.monto_total_pagar += monto_mora
                    p.save()
                    
                    conteo_aplicados += 1

        self.stdout.write(self.style.SUCCESS(f'Sincronización terminada: {conteo_aplicados} moras aplicadas el {hoy}'))

    def verificar_atraso_real(self, p, hoy):
        """
        Calcula las fechas de pago y revisa si alguna ya pasó y no tiene abono.
        """
        fecha_base = p.fecha_inicio
        # Aseguramos que sea objeto date
        if hasattr(fecha_base, 'date'):
            fecha_base = fecha_base.date()

        for i in range(1, p.cuotas + 1):
            # 7. Ajuste de modalidad según los nombres en tu Admin (Semanal, Quincenal, Mensual)
            if p.modalidad == "Semanal":
                fecha_pago = fecha_base + timedelta(weeks=i)
            elif p.modalidad == "Quincenal":
                fecha_pago = fecha_base + timedelta(days=15 * i)
            elif p.modalidad == "Mensual":
                fecha_pago = fecha_base + timedelta(days=30 * i)
            else:
                # Caso por defecto para modalidades cortas (S, Q, M)
                if p.modalidad == "S":
                    fecha_pago = fecha_base + timedelta(weeks=i)
                else:
                    fecha_pago = fecha_base + timedelta(weeks=i)

            # Ajuste de domingo a lunes (opcional, para no cobrar multas en domingo)
            if fecha_pago.weekday() == 6:
                fecha_pago += timedelta(days=1)

            # Si la cuota ya venció (fecha_pago < hoy)
            if fecha_pago <= hoy:
                # 8. Revisamos si existe el abono para esa semana específica
                pagado = p.abonos.filter(semana_numero=i).exists()
                if not pagado:
                    return True # Confirmamos el atraso
        
        return False