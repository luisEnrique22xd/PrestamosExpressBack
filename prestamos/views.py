from datetime import datetime, date, timedelta
from decimal import Decimal

from django.utils import timezone
from django.db.models import Sum, Count, DecimalField
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth

from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import Prestamo, Cliente, Abono, Penalizacion
from .serializers import ClienteSerializer, PrestamoSerializer, AbonoSerializer


# ==============================
# ESTADÍSTICAS GLOBALES
# ==============================

@api_view(['GET'])
def estadisticas_globales(request):

    definicion_rangos = [
        {"label": "$500-1500", "min": 500, "max": 1500},
        {"label": "$1501-3000", "min": 1501, "max": 3000},
        {"label": "$3001-5000", "min": 3001, "max": 5000},
        {"label": "$5001-7500", "min": 5001, "max": 7500},
        {"label": "$7501-10000", "min": 7501, "max": 10000},
    ]

    prestamos = Prestamo.objects.annotate(
        total_abonado=Coalesce(Sum('abonos__monto'), Decimal('0.00'), output_field=DecimalField())
    )

    rangos_data = []

    total_recuperado = Decimal("0.00")
    capital_en_calle = Decimal("0.00")
    prestamos_activos = 0

    for r in definicion_rangos:
        rangos_data.append({
            "label": r["label"],
            "min": r["min"],
            "max": r["max"],
            "total": Decimal("0.00"),
            "cant": 0
        })

    for p in prestamos:

        saldo = round(p.monto_total_pagar - p.total_abonado, 2)
        total_recuperado += p.total_abonado

        if saldo > Decimal("0.01"):

            prestamos_activos += 1
            capital_en_calle += saldo
            capital = p.monto_capital

            for r in rangos_data:
                if r["min"] <= capital <= r["max"]:
                    r["cant"] += 1
                    r["total"] += saldo
                    break

    for r in rangos_data:
        r["total"] = f"${r['total']:,.2f}"
        del r["min"]
        del r["max"]

    return Response({
        "prestamos_activos": prestamos_activos,
        "capital_en_calle": f"${capital_en_calle:,.2f}",
        "total_recuperado": f"${total_recuperado:,.2f}",
        "rangos": rangos_data
    })


# ==============================
# CLIENTES
# ==============================

class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer


class ClienteDetailView(generics.RetrieveAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer


# ==============================
# PRÉSTAMOS
# ==============================

class PrestamoListCreateView(generics.ListCreateAPIView):
    queryset = Prestamo.objects.all().order_by('-id')
    serializer_class = PrestamoSerializer


# ==============================
# ABONOS
# ==============================

class RegistrarAbonoView(generics.CreateAPIView):
    queryset = Abono.objects.all()
    serializer_class = AbonoSerializer


# ==============================
# ESTADÍSTICAS DINÁMICAS (GRÁFICAS)
# ==============================

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
            .annotate(
                activos=Count('id'),
                interes=Sum('tasa_interes')
            )
            .order_by('fecha')
        )

        resultado = [
            {
                "name": d['fecha'].strftime(formato),
                "activos": d['activos'],
                "interes": float(d['interes'] or 0) / d['activos'] if d['activos'] > 0 else 0
            }
            for d in datos
        ]

        return Response(resultado)


# ==============================
# CALENDARIO DE PAGOS
# ==============================

def to_date(value):
    if isinstance(value, datetime):
        return value.date()
    return value


class CalendarioPagosView(APIView):

    def get(self, request):

        hoy = date.today()

        mes = int(request.query_params.get("mes", hoy.month))
        anio = int(request.query_params.get("anio", hoy.year))

        proyecciones = []

        prestamos = Prestamo.objects.filter(activo=True).select_related(
            "cliente"
        ).prefetch_related("abonos")

        for p in prestamos:

            fecha_base = to_date(p.fecha_inicio)

            for i in range(1, p.cuotas + 1):

                if p.modalidad == "S":
                    fecha_pago = fecha_base + timedelta(weeks=i)

                elif p.modalidad == "Q":
                    fecha_pago = fecha_base + timedelta(days=15 * i)

                else:
                    fecha_pago = fecha_base + timedelta(days=30 * i)

                fecha_pago = to_date(fecha_pago)

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


# ==============================
# CONDONAR MORA
# ==============================

@api_view(['POST'])
def condonar_mora(request, pk):

    try:
        penalizacion = Penalizacion.objects.get(pk=pk)
        motivo = request.data.get('motivo')

        if not motivo or len(motivo) < 10:
            return Response(
                {"error": "Debes proporcionar un motivo válido (mín. 10 caracteres)"},
                status=400
            )

        penalizacion.activa = False
        penalizacion.motivo_condonacion = motivo
        penalizacion.fecha_condonacion = timezone.now()
        penalizacion.save()

        prestamo = penalizacion.prestamo
        prestamo.monto_total_pagar -= penalizacion.monto_penalizado
        prestamo.save()

        return Response({"message": "Penalización condonada correctamente"})

    except Penalizacion.DoesNotExist:
        return Response({"error": "No existe el registro"}, status=404)