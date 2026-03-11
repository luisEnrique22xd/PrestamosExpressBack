# prestamos/views.py
from urllib import request

from django.utils import timezone
from rest_framework import generics
from django.db.models import Sum, Count, Q
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Abono, Cliente, Penalizacion, Prestamo
from datetime import datetime, timedelta
from rest_framework.views import APIView
from rest_framework.decorators import api_view
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from .serializers import AbonoSerializer, ClienteSerializer, PrestamoSerializer

# Vista para Clientes (La que ya tenías)
class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

# NUEVA Vista para Préstamos
class PrestamoListCreateView(generics.ListCreateAPIView):
    queryset = Prestamo.objects.all().order_by('-id')
    serializer_class = PrestamoSerializer
    
class ClienteDetailView(generics.RetrieveAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer

# prestamos/views.py
class RegistrarAbonoView(generics.CreateAPIView):
    queryset = Abono.objects.all()
    serializer_class = AbonoSerializer

class EstadisticasGlobalesView(APIView):
    def get(self, request):
        total_recuperado = Abono.objects.aggregate(total=Sum('monto'))['total'] or 0
        
        def obtener_datos_rango(min_v, max_v):
            qs = Prestamo.objects.filter(monto_capital__gte=min_v, monto_capital__lte=max_v)
            return {
                "label": f"${min_v}-{max_v}",
                "total": f"${qs.aggregate(Sum('monto_capital'))['monto_capital__sum'] or 0:,.2f}",
                "cant": qs.count()
            }

        rangos = [
            obtener_datos_rango(500, 1500),
            obtener_datos_rango(1501, 3000),
            obtener_datos_rango(3001, 5000),
            obtener_datos_rango(5001, 7500),
            obtener_datos_rango(7501, 10000),
        ]

        return Response({
            "total_recuperado": f"${total_recuperado:,.2f}",
            "rangos": rangos
        })

# VISTA 2: PARA LA GRÁFICA FILTRABLE
class EstadisticasDinamicasView(APIView):
    def get(self, request):
        periodo = request.query_params.get('periodo', 'semana')
        hoy = datetime.now()

        if periodo == 'semana':
            inicio = hoy - timedelta(days=7)
            truncado = TruncDay('fecha_creacion')
            formato = "%a"
        elif periodo == 'mes':
            inicio = hoy - timedelta(days=30)
            truncado = TruncWeek('fecha_creacion')
            formato = "Sem %W"
        else:
            inicio = hoy - timedelta(days=365)
            truncado = TruncMonth('fecha_creacion')
            formato = "%b"

        datos = (
            Prestamo.objects.filter(fecha_creacion__gte=inicio)
            .annotate(fecha=truncado)
            .values('fecha')
            .annotate(activos=Count('id'), interes=Sum('tasa_interes'))
            .order_by('fecha')
        )

        resultado = [
            {
                "name": d['fecha'].strftime(formato),
                "activos": d['activos'],
                "interes": float(d['interes'] or 0) / d['activos'] if d['activos'] > 0 else 0
            } for d in datos
        ]
        return Response(resultado)
    

class CalendarioPagosView(APIView):
    def get(self, request):
        hoy = timezone.now().date()
        prestamos = Prestamo.objects.filter(activo=True)
        proyecciones = []

        for p in prestamos:
            # Obtenemos los números de semana que ya han sido pagados para este préstamo
            semanas_pagadas = list(p.abonos.values_list('semana_numero', flat=True))

            for i in range(1, p.cuotas + 1):
                fecha_pago = p.fecha_inicio + timedelta(weeks=i)
                monto_cuota = p.monto_total_pagar / p.cuotas
                
                # --- DETERMINAR ESTATUS ---
                if i in semanas_pagadas:
                    estatus = 'pagado'
                elif fecha_pago < hoy:
                    estatus = 'vencido'
                else:
                    estatus = 'pendiente'

                proyecciones.append({
                    "id": f"{p.id}-{i}",
                    "cliente": p.cliente.nombre,
                    "fecha": fecha_pago.strftime('%a %b %d %Y'),
                    "monto": round(monto_cuota, 2),
                    "idCliente": p.cliente.id,
                    "tel": p.cliente.telefono,
                    "estatus": estatus, # <--- Enviamos el color lógico
                    "num_semana": i
                })
        
        return Response(proyecciones)
@api_view(['POST'])
def condonar_mora(request, pk):
    try:
        penalizacion = Penalizacion.objects.get(pk=pk)
        motivo = request.data.get('motivo')

        if not motivo or len(motivo) < 10:
            return Response({"error": "Debes proporcionar un motivo válido (mín. 10 caracteres)"}, status=400)

        # Marcamos como inactiva
        penalizacion.activa = False
        penalizacion.motivo_condonacion = motivo
        penalizacion.fecha_condonacion = timezone.now()
        penalizacion.save()

        # Importante: Restamos el monto del total a pagar del préstamo
        prestamo = penalizacion.prestamo
        prestamo.monto_total_pagar -= penalizacion.monto_penalizado
        prestamo.save()

        return Response({"message": "Penalización condonada correctamente"})
    except Penalizacion.DoesNotExist:
        return Response({"error": "No existe el registro"}, status=404)

from datetime import datetime, date, timedelta

from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Prestamo


def to_date(value):
    """Convierte datetime o date a date."""
    if isinstance(value, datetime):
        return value.date()
    return value


class CalendarioPagosView(APIView):

    def get(self, request):

        hoy = date.today()

        mes = int(request.query_params.get("mes", hoy.month))
        anio = int(request.query_params.get("anio", hoy.year))

        proyecciones = []

        prestamos = Prestamo.objects.filter(activo=True).select_related("cliente").prefetch_related("abonos")

        for p in prestamos:

            fecha_base = to_date(p.fecha_inicio)

            for i in range(1, p.cuotas + 1):

                # calcular fecha
                if p.modalidad == "S":
                    fecha_pago = fecha_base + timedelta(weeks=i)

                elif p.modalidad == "Q":
                    fecha_pago = fecha_base + timedelta(days=15 * i)

                else:
                    fecha_pago = fecha_base + timedelta(days=30 * i)

                # asegurar tipo date
                fecha_pago = to_date(fecha_pago)

                # mover si cae domingo
                if fecha_pago.weekday() == 6:
                    fecha_pago += timedelta(days=1)

                if fecha_pago.month == mes and fecha_pago.year == anio:

                    ya_pagado = p.abonos.filter(semana_numero=i).exists()

                    if ya_pagado:
                        estatus = "pagado"

                    elif fecha_pago < hoy:
                        estatus = "vencido"

                    else:
                        estatus = "pendiente"

                    proyecciones.append({
                        "id": f"{p.id}-{i}",
                        "cliente": p.cliente.nombre,
                        "idCliente": p.cliente.id,
                        "tel": p.cliente.telefono,
                        "fecha": fecha_pago.strftime("%Y-%m-%d"),
                        "monto": round(p.monto_total_pagar / p.cuotas, 2),
                        "estatus": estatus
                    })

        return Response(proyecciones)