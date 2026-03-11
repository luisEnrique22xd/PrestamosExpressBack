# prestamos/services.py
from datetime import date
from .models import Prestamo, Penalizacion

def aplicar_penalizaciones_diarias():
    hoy = date.today()
    # Buscamos préstamos activos
    prestamos = Prestamo.objects.filter(activo=True)
    
    for p in prestamos:
        # 1. Buscamos si tiene cuotas vencidas al día de hoy que no estén pagadas
        # Esta lógica depende de tu tabla de proyecciones
        tiene_vencidos = p.proyecciones.filter(fecha__lt=hoy, pagado=False).exists()
        
        if tiene_vencidos:
            # 2. Calculamos el 1.5% del monto_capital (monto inicial)
            monto_recargo = float(p.monto_capital) * 0.015
            
            # 3. Verificamos que no se haya aplicado ya una penalización hoy
            ya_penalizado = p.penalizaciones.filter(fecha_aplicacion=hoy).exists()
            
            if not ya_penalizado:
                # 4. Registramos la penalización
                Penalizacion.objects.create(
                    prestamo=p,
                    monto_penalizado=monto_recargo
                )
                # 5. Actualizamos el monto_total_pagar del préstamo
                p.monto_total_pagar += monto_recargo
                p.save()
def condonar_penalizacion(penalizacion_id, motivo):
    penalizacion = Penalizacion.objects.get(id=penalizacion_id)
    if penalizacion.activa:
        # 1. Restamos el monto del total del préstamo
        prestamo = penalizacion.prestamo
        prestamo.monto_total_pagar -= penalizacion.monto_penalizado
        
        # 2. Desactivamos la penalización
        penalizacion.activa = False
        penalizacion.motivo_condonacion = motivo
        
        prestamo.save()
        penalizacion.save()