from datetime import datetime, date, timedelta
from decimal import Decimal
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.utils import timezone
from django.db.models import Max, Sum, Count, DecimalField
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth
from rest_framework import status
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

from .models import ContadorFolio, Prestamo, Cliente, Abono, Penalizacion, registrar_log, Grupo
from .serializers import ClienteSerializer, DirectorioHibridoSerializer, PrestamoSerializer, AbonoSerializer


# ==============================
# ESTADÍSTICAS GLOBALES
# ==============================

@api_view(['GET'])
def estadisticas_globales(request):
    hoy = timezone.now().date()
    cobrado_hoy = Abono.objects.filter(fecha_pago=hoy).aggregate(Sum('monto'))['monto__sum'] or 0.0

    # 2. Total Recuperado (Suma histórica de abonos)
    total_recuperado = Abono.objects.aggregate(Sum('monto'))['monto__sum'] or 0.0

    # 3. Moras por recuperar (Suma de penalizaciones activas)
    total_moras_pendientes = Penalizacion.objects.filter(activa=True).aggregate(
        Sum('monto_penalizado')
    )['monto_penalizado__sum'] or 0.0

    # 4. Préstamos activos
    prestamos_activos = Prestamo.objects.filter(activo=True).count()
    total_prestado = Prestamo.objects.filter(activo=True).aggregate(Sum('monto_capital'))['monto_capital__sum'] or 0
    total_moras_pendientes = Penalizacion.objects.filter(activa=True).aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0.0

    # 2. Cambiamos 'monto_total' por 'monto_total_pagar'
    total_esperado = Prestamo.objects.filter(activo=True).aggregate(Sum('monto_total_pagar'))['monto_total_pagar__sum'] or 0
    total_interes_pactado = total_esperado - total_prestado

    # 3. Lo demás se queda igual (asegúrate de que Penalizacion tenga monto_penalizado)
    total_moras = Penalizacion.objects.aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0
    total_recuperado_abonos = Abono.objects.aggregate(Sum('monto'))['monto__sum'] or 0

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

    hoy = timezone.now().date()
    hace_7_dias = hoy - timedelta(days=6)
    
    # Consultamos los abonos de la última semana
    abonos_ultimos_7_dias = (
        Abono.objects.filter(fecha_pago__gte=hace_7_dias) # Asegúrate que tu campo se llame fecha_pago o fecha
        .annotate(dia=TruncDay('fecha_pago'))
        .values('dia')
        .annotate(total=Sum('monto'))
        .order_by('dia')
    )

    # Creamos un diccionario para mapear los días (0=Lun, 1=Mar, etc.)
    dias_nombres = {0: 'Lun', 1: 'Mar', 2: 'Mie', 3: 'Jue', 4: 'Vie', 5: 'Sab', 6: 'Dom'}
    
    # Generamos la lista completa de 7 días (aunque tengan $0)
    grafica_semanal = []
    for i in range(7):
        # i de 0 a 6 para ir del pasado al presente
        fecha_iterada = hace_7_dias + timedelta(days=i)
        
        # Buscamos el monto en los resultados de la DB
        monto_dia = 0
        for item in abonos_ultimos_7_dias:
            if item['dia'] == fecha_iterada:
                monto_dia = item['total']
                break
        
        grafica_semanal.append({
            "dia": dias_nombres[fecha_iterada.weekday()],
            "monto": float(monto_dia)
        })
    monto_hoy = sum(float(item['monto']) for item in grafica_semanal if item['dia'] == dias_nombres[hoy.weekday()])

    return Response({
        "prestamos_activos": prestamos_activos,
        "capital_en_calle": f"${capital_en_calle:,.2f}",
        "total_recuperado": f"${total_recuperado:,.2f}",
        "rangos": rangos_data,
        "total_interes_generado": total_interes_pactado, # <--- Agrega este
        "total_penalizaciones": total_moras,            # <--- Y este
        "rangos": rangos_data,
        "grafica_semanal": grafica_semanal, # <--- ¡ESTA ES LA QUE FALTA!
        "cobrado_hoy": f"${sum(item['total'] for item in abonos_ultimos_7_dias if item['dia'] == hoy):,.2f}",
        "total_moras_pendientes": f"${total_moras_pendientes:,.2f}"
        
    })


# ==============================
# CLIENTES
# ==============================

class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    
    def perform_create(self, serializer):
        cliente = serializer.save()
        # Log: Registro de nuevo cliente
        registrar_log(
            self.request.user, 
            "REGISTRO_CLIENTE", 
            f"Se dio de alta al cliente: {cliente.nombre} (ID: {cliente.id})"
        )

class ClienteDetailView(generics.RetrieveAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer


# ==============================
# PRÉSTAMOS
# ==============================
# Reemplaza esta clase completa en tu views.py
class PrestamoListCreateView(generics.ListCreateAPIView):
    queryset = Prestamo.objects.all().order_by('-id')
    serializer_class = PrestamoSerializer
    
    def create(self, request, *args, **kwargs):
        # 1. Extraemos el ID del cliente de los datos recibidos
        cliente_id = request.data.get('cliente')
        tipo = request.data.get('tipo', 'I')

        # 2. Solo validamos moras si es un préstamo Individual
        if tipo == 'I' and cliente_id:
            tiene_moras = Penalizacion.objects.filter(
                prestamo__cliente_id=cliente_id, 
                activa=True
            ).exists()

            if tiene_moras:
                return Response({
                    "error": "BLOQUEO DE CRÉDITO: El cliente tiene multas pendientes de pago. Debe liquidar sus recargos antes de solicitar un nuevo préstamo."
                }, status=status.HTTP_403_FORBIDDEN)

        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # 1. Extraemos los datos del request
        tipo = self.request.data.get('tipo', 'I')
        nombre_grupo = self.request.data.get('nombre_grupo')
        ids_integrantes = self.request.data.get('integrantes', [])
        
        grupo_obj = None

        # 2. Lógica para Préstamos Grupales
        if tipo == 'G' and nombre_grupo:
            # Usamos get_or_create para evitar duplicados del mismo nombre
            grupo_obj, created = Grupo.objects.get_or_create(nombre_grupo=nombre_grupo)
            
            # Si el grupo es nuevo o queremos actualizar sus integrantes
            if ids_integrantes:
                clientes = Cliente.objects.filter(id__in=ids_integrantes)
                grupo_obj.integrantes.set(clientes)

        # 3. Guardamos el préstamo con los vínculos correctos
        # Si es individual, grupo será None. Si es grupal, cliente será None.
        prestamo = serializer.save(
            tipo=tipo,
            grupo=grupo_obj,
            cliente=None if tipo == 'G' else serializer.validated_data.get('cliente')
        )

        # 4. Log de Auditoría
        # Definimos quién es el sujeto para el log sin que explote si cliente es None
        if tipo == 'G':
            sujeto = f"Grupo: {nombre_grupo}"
        else:
            sujeto = f"Socio: {prestamo.cliente.nombre}" if prestamo.cliente else "N/A"

        registrar_log(
            self.request.user, 
            "EMISION_PRESTAMO", 
            f"Préstamo {prestamo.get_tipo_display()} #{prestamo.id} creado para {sujeto}"
        )

# ==============================
# ABONOS
# ==============================

class RegistrarAbonoView(generics.CreateAPIView):
    queryset = Abono.objects.all()
    serializer_class = AbonoSerializer
    
    def create(self, request, *args, **kwargs):
        # 1. Extraemos el dinero destinado a multas
        monto_multa_pagado = Decimal(request.data.get('monto_penalizacion', '0.00'))
        prestamo_id = request.data.get('prestamo')
        
        # 2. Si pagó multas, las desactivamos en la DB
        if monto_multa_pagado > 0:
            Penalizacion.objects.filter(prestamo_id=prestamo_id, activa=True).update(activa=False)

        # 3. Guardar el abono normal al capital
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prestamo = serializer.validated_data['prestamo']
        
        # Calculamos saldos antes de guardar
        total_pagado_antes = prestamo.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
        saldo_anterior = prestamo.monto_total_pagar - total_pagado_antes
        
        self.perform_create(serializer)
        abono = serializer.instance
        
        # 4. Respuesta completa para el Ticket
        sujeto = prestamo.grupo.nombre_grupo if prestamo.tipo == 'G' else prestamo.cliente.nombre
        
        return Response({
            "id": abono.id,
            "monto": float(abono.monto),
            "multas_pagadas": float(monto_multa_pagado), # <--- DATO CLAVE PARA EL TICKET
            "saldo_anterior": float(saldo_anterior),
            "nuevo_saldo": float(prestamo.monto_total_pagar - (total_pagado_antes + abono.monto)),
            "cliente": sujeto,
            "fecha": abono.fecha_pago.strftime("%d/%m/%Y"),
            "hora": timezone.localtime(timezone.now()).strftime("%H:%M:%S")
        }, status=status.HTTP_201_CREATED)

# ==============================
# ESTADÍSTICAS DINÁMICAS (GRÁFICAS)
# ==============================

class EstadisticasDinamicasView(APIView):
    def get(self, request):
        periodo = request.query_params.get('periodo', 'semana')
        hoy = timezone.now()

        if periodo == 'semana':
            inicio = hoy - timedelta(days=7)
            truncado = TruncDay('fecha_creacion')
            formato = "%a" # Lun, Mar...
        elif periodo == 'mes':
            inicio = hoy - timedelta(days=30)
            truncado = TruncMonth('fecha_creacion')
            formato = "%b" # Ene, Feb...
        else:
            inicio = hoy - timedelta(days=365)
            truncado = TruncMonth('fecha_creacion')
            formato = "%b %Y"

        datos = (
            Prestamo.objects.filter(fecha_creacion__gte=inicio)
            .annotate(fecha_truncada=truncado)
            .values('fecha_truncada')
            .annotate(
                # 🔥 AQUÍ ESTÁ EL CAMBIO: Sumamos dinero, no contamos IDs
              
                total_capital=Sum('monto_capital'), 
                total_interes=Sum('monto_total_pagar') - Sum('monto_capital')
            )
            .order_by('fecha_truncada')
        )

        resultado = [
            {
                "name": d['fecha_truncada'].strftime(formato),
                # Mandamos números puros para que Recharts haga la magia
                "capital": float(d['total_capital'] or 0),
                "interes": float(d['total_interes'] or 0)
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
@permission_classes([IsAdminUser])
def condonar_mora(request, pk):
    try:
        # 1. Obtener la penalización y definir el préstamo DESDE EL INICIO
        penalizacion = Penalizacion.objects.get(pk=pk)
        prestamo = penalizacion.prestamo  # <-- Definimos 'prestamo' aquí
        
        # 2. Validar el motivo ANTES de hacer cualquier cálculo
        motivo = request.data.get('motivo')
        if not motivo or len(motivo) < 10:
            return Response(
                {"error": "Debes proporcionar un motivo válido (mín. 10 caracteres)"},
                status=400
            )

        # 3. Solo restamos si la penalización está activa (para evitar restar doble si le dan clic dos veces)
        if penalizacion.activa:
            monto_a_restar = penalizacion.monto_penalizado
            
            # Restamos del préstamo
            prestamo.monto_total_pagar -= monto_a_restar
            prestamo.save()

            # Actualizamos la penalización
            penalizacion.activa = False
            penalizacion.motivo_condonacion = motivo
            penalizacion.fecha_condonacion = timezone.now()
            penalizacion.save()

            # Registramos el log
            registrar_log(
                request.user, 
                "CONDONACION_MORA", 
                f"Se perdonaron ${monto_a_restar} a {prestamo.cliente.nombre}. Motivo: {motivo}"
            )

            return Response({"message": "Penalización condonada y saldo actualizado"})
        
        else:
            return Response({"message": "Esta penalización ya había sido condonada anteriormente"}, status=400)

    except Penalizacion.DoesNotExist:
        return Response({"error": "No existe el registro"}, status=404)
    except Exception as e:
        return Response({"error": f"Error inesperado: {str(e)}"}, status=500)
    
@api_view(['GET', 'POST'])
def obtener_proximo_folio(request):
    try:
        # get_or_create intenta buscar el ID 1, si no existe lo crea con numero 1
        contador, created = ContadorFolio.objects.get_or_create(
            id=1, 
            defaults={'numero_actual': 1}
        )
        
        if request.method == 'POST':
            folio_a_usar = contador.numero_actual
            contador.numero_actual += 1
            contador.save()
            return Response({'folio': folio_a_usar})
        
        # Para el GET devolvemos proximo_folio para que tu Frontend no truene
        return Response({'proximo_folio': contador.numero_actual})

    except Exception as e:
        # Si algo falla, devolvemos un error claro en lugar de un 500 genérico
        return Response({"error": str(e)}, status=500)
@api_view(['GET'])
def directorio_hibrido(request):
    search = request.query_params.get('search', '').lower()
    
    # 1. Obtenemos Clientes
    clientes = Cliente.objects.all()
    if search:
        clientes = clientes.filter(nombre__icontains=search)
    
    # 2. Obtenemos Grupos
    grupos = Grupo.objects.all()
    if search:
        grupos = grupos.filter(nombre_grupo__icontains=search)

    # 3. Marcamos quién es quién
    data_clientes = []
    for c in clientes:
        c.es_grupo = False
        data_clientes.append(c)
        
    data_grupos = []
    for g in grupos:
        g.es_grupo = True
        data_grupos.append(g)

    # 4. Unificamos y Serializamos
    lista_final = data_clientes + data_grupos
    # Ordenamos por ID de forma descendente para ver lo más nuevo arriba
    lista_final.sort(key=lambda x: x.id, reverse=True)
    
    serializer = DirectorioHibridoSerializer(lista_final, many=True)
    return Response(serializer.data)
@api_view(['GET'])
def detalle_grupo(request, pk):
    try:
        from django.db.models import Sum
        grupo = Grupo.objects.get(pk=pk)
        # Buscamos el préstamo activo del grupo
        prestamo = Prestamo.objects.filter(grupo=grupo, activo=True).order_by('-id').first()
        
        # Estructura "Espejo" para que el Dashboard de Clientes funcione
        data = {
            "id": grupo.id,
            "nombre": grupo.nombre_grupo, # El front busca 'nombre'
            "direccion": "Crédito Grupal Solidario",
            "telefono": "N/A",
            "tipo": "G",
            "numero_prestamos": Prestamo.objects.filter(grupo=grupo).count(),
            "tiene_prestamo_activo": prestamo is not None,
            "ultimo_prestamo_id": prestamo.id if prestamo else None,
            "saldo_actual": 0,
            "progreso_pagos": None,
            "penalizaciones": [],
            "integrantes_detalle": ClienteSerializer(grupo.integrantes.all(), many=True).data,
        }

        if prestamo:
            total_abonado = Abono.objects.filter(prestamo=prestamo).aggregate(Sum('monto'))['monto__sum'] or 0
            saldo = float(prestamo.monto_total_pagar) - float(total_abonado)
            
            data["saldo_actual"] = saldo
            data["nombre_aval"] = prestamo.nombre_aval
            data["parentesco_aval"] = prestamo.parentesco_aval
            data["garantia_descripcion"] = prestamo.garantia_descripcion
            
            abonos_data = Abono.objects.filter(prestamo=prestamo).order_by('-id')
            data["historial_pagos"] = [
                {
                    "id": a.id,
                    "monto": float(a.monto),
                    "fecha": a.fecha_pago.strftime("%d/%m/%Y"),
                    "semana": a.semana_numero,
                } for a in abonos_data
            ]

            data["progreso_pagos"] = {
                "monto_capital": float(prestamo.monto_capital),
                "monto_pagado": float(total_abonado),
                "modalidad": prestamo.modalidad,
                "total_cuotas": prestamo.cuotas,
                "pagado": (float(total_abonado) / float(prestamo.monto_total_pagar)) * 100 if prestamo.monto_total_pagar > 0 else 0
            }
            # Opcional: Serializar penalizaciones si las hay
            # data["penalizaciones"] = PenalizacionSerializer(prestamo.penalizaciones.all(), many=True).data

        return Response(data)
    except Grupo.DoesNotExist:
        return Response({"error": "Grupo no encontrado"}, status=404)
@api_view(['GET'])
def cartera_vencida_hibrida(request):
    # Buscamos préstamos activos cuya fecha de próximo pago ya pasó
    hoy = timezone.now()
    prestamos_mora = Prestamo.objects.filter(activo=True, fecha_proximo_pago__lt=hoy)
    
    data_vencida = []
    for p in prestamos_mora:
        # Detectamos el nombre (Socio o Grupo)
        nombre_deudor = p.grupo.nombre_grupo if p.tipo == 'G' else p.cliente.nombre
        
        data_vencida.append({
            "prestamo_id": p.id,
            "tipo": p.tipo, # 'I' o 'G'
            "deudor": nombre_deudor,
            "monto_atrasado": p.monto_cuota, # O el cálculo que uses
            "dias_atraso": (hoy - p.fecha_proximo_pago).days,
            "es_grupo": p.tipo == 'G'
        })
        
    return Response(data_vencida)
@api_view(['GET'])
def cartera_vencida_hibrida(request):
    from datetime import timedelta
    hoy = timezone.now()
    
    # 1. Traemos TODOS los préstamos activos
    prestamos_activos = Prestamo.objects.filter(activo=True)
    data_cartera = []

    for p in prestamos_activos:
        # 2. Calculamos la fecha en la que debió pagar
        # Si no tienes lógica de cuotas en el modelo, usamos la fecha_inicio + el intervalo
        ultimo_abono = p.abonos.order_by('-fecha_pago').first()
        
        # Si hubo abonos, la fecha base es el último abono, si no, es la fecha_inicio
        fecha_referencia = ultimo_abono.fecha_pago if ultimo_abono else p.fecha_inicio
        
        # Determinamos el intervalo según modalidad
        dias_intervalo = 7 if p.modalidad == 'S' else 15 if p.modalidad == 'Q' else 30
        fecha_vencimiento = fecha_referencia + timedelta(days=dias_intervalo)

        # 3. ¿Está vencido?
        if fecha_vencimiento < hoy:
            es_grupo = (p.tipo == 'G')
            id_entidad = p.grupo.id if es_grupo else p.cliente.id
            nombre = p.grupo.nombre_grupo if es_grupo else p.cliente.nombre
            
            # Calculamos días de atraso
            dias_atraso = (hoy - fecha_vencimiento).days

            data_cartera.append({
                "id_prestamo": p.id,
                "id_entidad": id_entidad,
                "nombre_deudor": nombre,
                "es_grupo": es_grupo,
                "monto_vencido": p.monto_total_pagar / p.cuotas, # Estimado de una cuota
                "dias_atraso": dias_atraso,
                "fecha_vencimiento": fecha_vencimiento,
                "num_cuota": (p.abonos.count() + 1),
                "telefono": p.telefono_aval if es_grupo else p.cliente.telefono
            })

    # Ordenamos por los que tienen más días de atraso
    data_cartera.sort(key=lambda x: x['dias_atraso'], reverse=True)
    
    return Response(data_cartera)