from datetime import datetime, date, timedelta
from decimal import Decimal
import pytz
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from django.utils import timezone
from django.db.models import Max, Sum, Count, DecimalField, Q
from django.db.models.functions import Coalesce, TruncDay, TruncWeek, TruncMonth
from rest_framework import status
from rest_framework import generics
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes

from .models import ContadorFolio, Prestamo, Cliente, Abono, Penalizacion, registrar_log, Grupo
from .serializers import ClienteSerializer, DirectorioHibridoSerializer, PrestamoSerializer, AbonoSerializer


from django.http import JsonResponse
from django.db.models import Sum
from rest_framework.decorators import api_view # Opcional, pero recomendado
# Asegúrate de importar tus modelos y serializers

def detalle_grupo(request, pk):
    try:
        # 1. Buscamos el grupo
        grupo = Grupo.objects.get(pk=pk)
        
        # 2. Buscamos préstamo activo
        prestamo = Prestamo.objects.filter(grupo=grupo, activo=True).first()
        
        # 3. Serializamos integrantes
        integrantes_data = ClienteSerializer(grupo.integrantes.all(), many=True).data
        
        data = {
            "id": grupo.id, 
            "nombre": grupo.nombre_grupo, 
            "tipo": "G", 
            "tiene_prestamo_activo": prestamo is not None, 
            "integrantes_detalle": integrantes_data
        }
        
        if prestamo:
            # 4. Cálculo de saldo (Sum debe estar importado de django.db.models)
            tot = Abono.objects.filter(prestamo=prestamo).aggregate(Sum('monto'))['monto__sum'] or 0
            data["saldo_actual"] = float(prestamo.monto_total_pagar) - float(tot)
            data["nombre_aval"] = prestamo.nombre_aval
            data["monto_total_pagar"] = float(prestamo.monto_total_pagar)
        
        # 🚨 LA CLAVE: Usa JsonResponse en lugar de Response
        return JsonResponse(data)

    except Grupo.DoesNotExist:
        return JsonResponse({"error": "Grupo no encontrado"}, status=404)
    except Exception as e:
        # Esto te ayudará a ver otros errores en los logs
        return JsonResponse({"error": str(e)}, status=500)
    
# ==============================
# ESTADÍSTICAS GLOBALES
# ==============================

@api_view(['GET'])
def estadisticas_globales(request):
    # 1. Configuración de Zona Horaria (Evita el desfase de Railway/UTC)
    mexico_tz = pytz.timezone('America/Mexico_City')
    ahora_mexico = timezone.now().astimezone(mexico_tz)
    hoy_mexico = ahora_mexico.date()

    # 2. Cobranza del día (Filtrado por la fecha real en México)
    cobrado_hoy = Abono.objects.filter(
        fecha_pago=hoy_mexico
    ).aggregate(Sum('monto'))['monto__sum'] or 0.0

    desglose_hoy = Abono.objects.filter(fecha_pago=hoy_mexico).values('modalidad').annotate(
        total=Sum('monto')
    ).order_by('modalidad')
    # Mapeo de siglas a nombres reales
    nombres_modalidad = {'E': 'Efectivo', 'D': 'Depósito', 'T': 'Transferencia'}
    
    # Formateamos para el frontend
    metodos_pago_data = []
    for item in desglose_hoy:
        metodos_pago_data.append({
            "label": nombres_modalidad.get(item['modalidad'], 'Otro'),
            "monto": float(item['total'] or 0)
        })
    # 3. Métricas históricas y acumuladas
    total_recuperado_hist = Abono.objects.aggregate(Sum('monto'))['monto__sum'] or 0.0

    total_moras_pendientes = Penalizacion.objects.filter(
        activa=True
    ).aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0.0

    prestamos_activos_count = Prestamo.objects.filter(activo=True).count()
    
    total_prestado = Prestamo.objects.filter(
        activo=True
    ).aggregate(Sum('monto_capital'))['monto_capital__sum'] or 0
    
    total_esperado = Prestamo.objects.filter(
        activo=True
    ).aggregate(Sum('monto_total_pagar'))['monto_total_pagar__sum'] or 0
    
    total_interes_pactado = total_esperado - total_prestado
    
    total_moras_historicas = Penalizacion.objects.aggregate(
        Sum('monto_penalizado')
    )['monto_penalizado__sum'] or 0

    # 4. Clasificación por Rangos de Inversión
    definicion_rangos = [
        {"label": "$500-1500", "min": 500, "max": 1500},
        {"label": "$1501-3000", "min": 1501, "max": 3000},
        {"label": "$3001-5000", "min": 3001, "max": 5000},
        {"label": "$5001-7500", "min": 5001, "max": 7500},
        {"label": "$7501-10000", "min": 7501, "max": 10000},
        {"label": "$10001-12500", "min": 10001, "max": 12500},
        {"label": "$12501-15000", "min": 12501, "max": 15000},
    ]

    # Traemos préstamos con sus abonos sumados para calcular el saldo en calle real
    prestamos = Prestamo.objects.filter(activo=True).annotate(
        total_abonado_calc=Coalesce(
            Sum('abonos__monto'), 
            Decimal('0.00'), 
            output_field=DecimalField()
        )
    )

    rangos_data = []
    capital_en_calle = Decimal("0.00")

    for r in definicion_rangos:
        rangos_data.append({
            "label": r["label"],
            "min": r["min"],
            "max": r["max"],
            "total": Decimal("0.00"),
            "cant": 0
        })

    for p in prestamos:
        # Saldo = Lo que debe pagar - Lo que ya abonó
        saldo = round(p.monto_total_pagar - p.total_abonado_calc, 2)
        if saldo > Decimal("0.01"):
            capital_en_calle += saldo
            for r in rangos_data:
                if r["min"] <= p.monto_capital <= r["max"]:
                    r["cant"] += 1
                    r["total"] += saldo
                    break

    # Formatear montos de los rangos para el frontend
    for r in rangos_data:
        r["total"] = f"${r['total']:,.2f}"
        del r["min"]
        del r["max"]

    # 5. Gráfica de Rendimiento Semanal (Últimos 7 días)
    hace_7_dias = hoy_mexico - timedelta(days=6)
    abonos_7 = Abono.objects.filter(
        fecha_pago__gte=hace_7_dias,
        fecha_pago__lte=hoy_mexico
    ).annotate(
        dia=TruncDay('fecha_pago')
    ).values('dia').annotate(
        total=Sum('monto')
    ).order_by('dia')

    dias_nombres = {0: 'Lun', 1: 'Mar', 2: 'Mie', 3: 'Jue', 4: 'Vie', 5: 'Sab', 6: 'Dom'}
    grafica_semanal = []
    
    for i in range(7):
        f_iter = hace_7_dias + timedelta(days=i)
        # Buscamos si hay abonos para ese día específico en la consulta
        monto_dia = next((item['total'] for item in abonos_7 if item['dia'] == f_iter), 0)
        grafica_semanal.append({
            "dia": dias_nombres[f_iter.weekday()], 
            "monto": float(monto_dia)
        })

    # 6. Respuesta final
    return Response({
        
        "metodos_pago": metodos_pago_data,
        "prestamos_activos": prestamos_activos_count,
        "capital_en_calle": f"${capital_en_calle:,.2f}",
        "total_recuperado": f"${total_recuperado_hist:,.2f}",
        "rangos": rangos_data,
        "total_interes_generado": total_interes_pactado,
        "total_penalizaciones": total_moras_historicas,
        "grafica_semanal": grafica_semanal,
        "cobrado_hoy": f"${cobrado_hoy:,.2f}",
        "total_moras_pendientes": total_moras_pendientes
    })

# ==============================
# CLIENTES
# ==============================

class ClienteListCreateView(generics.ListCreateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer
    read_only_fields = ['nombre', 'curp', 'fecha_nacimiento']
    
    def perform_create(self, serializer):
        cliente = serializer.save()
        registrar_log(self.request.user, "REGISTRO_CLIENTE", f"Se dio de alta al cliente: {cliente.nombre} (ID: {cliente.id})")

class ClienteDetailView(generics.RetrieveUpdateAPIView):
    queryset = Cliente.objects.all()
    serializer_class = ClienteSerializer


# ==============================
# PRÉSTAMOS
# ==============================

class PrestamoListCreateView(generics.ListCreateAPIView):
    queryset = Prestamo.objects.all().order_by('-id')
    serializer_class = PrestamoSerializer
    
    def create(self, request, *args, **kwargs):
        cliente_id = request.data.get('cliente')
        tipo = request.data.get('tipo', 'I')

        if tipo == 'I' and cliente_id:
            tiene_moras = Penalizacion.objects.filter(prestamo__cliente_id=cliente_id, activa=True).exists()
            if tiene_moras:
                return Response({
                    "error": "BLOQUEO DE CRÉDITO: El cliente tiene multas pendientes."
                }, status=status.HTTP_403_FORBIDDEN)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        tipo = self.request.data.get('tipo', 'I')
        nombre_grupo = self.request.data.get('nombre_grupo')
        ids_integrantes = self.request.data.get('integrantes', [])
        grupo_obj = None

        if tipo == 'G' and nombre_grupo:
            grupo_obj, created = Grupo.objects.get_or_create(nombre_grupo=nombre_grupo)
            if ids_integrantes:
                clientes = Cliente.objects.filter(id__in=ids_integrantes)
                grupo_obj.integrantes.set(clientes)

        prestamo = serializer.save(
            tipo=tipo,
            grupo=grupo_obj,
            cliente=None if tipo == 'G' else serializer.validated_data.get('cliente')
        )

        sujeto = f"Grupo: {nombre_grupo}" if tipo == 'G' else f"Socio: {prestamo.cliente.nombre}"
        registrar_log(self.request.user, "EMISION_PRESTAMO", f"Préstamo #{prestamo.id} creado para {sujeto}")


# ==============================
# ABONOS
# ==============================

class RegistrarAbonoView(generics.CreateAPIView):
    queryset = Abono.objects.all()
    serializer_class = AbonoSerializer
    
    def create(self, request, *args, **kwargs):
        monto_multa_pagado = Decimal(request.data.get('monto_penalizacion', '0.00'))
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prestamo = serializer.validated_data['prestamo']
        
        # 1. Calculamos saldo ANTES del pago (Capital + Multas Activas)
        total_abonado_antes = prestamo.abonos.aggregate(Sum('monto'))['monto__sum'] or Decimal('0.00')
        saldo_cap_antes = prestamo.monto_total_pagar - total_abonado_antes
        
        m_activas = prestamo.penalizaciones.filter(activa=True)
        total_m_antes = m_activas.aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or Decimal('0.00')
        
        # El saldo que Alexander ve en pantalla antes de cobrar
        saldo_anterior_total = float(saldo_cap_antes + total_m_antes)

        # 2. PROCESO CRUCIAL: Desactivar multas si se pagaron
        if monto_multa_pagado > 0:
            prestamo.penalizaciones.filter(activa=True).update(activa=False)

        # 3. Guardar el Abono (Los $450 de Luis)
        self.perform_create(serializer)
        abono = serializer.instance
        
        # 4. CALCULO DEL NUEVO SALDO (La matemática de Alexander)
        # Saldo Nuevo = (Capital Anterior + Multas Anteriores) - Pago Total
        # Para Luis: (3600 + 90) - 450 = 3240 -> Pero Alexander quiere ver 3150 (Capital limpio)
        # Si queremos que vea $3,150, debemos mostrarle solo el saldo de capital restante:
        nuevo_saldo_final = float(saldo_cap_antes - abono.monto)

        # Registro de Log y Respuesta...
        sujeto = prestamo.grupo.nombre_grupo if prestamo.tipo == 'G' and prestamo.grupo else prestamo.cliente.nombre
        return Response({
            "id": abono.id,
            "monto": float(abono.monto),
            "penalizaciones_pagadas": float(monto_multa_pagado),
            "saldo_anterior": saldo_anterior_total,
            "nuevo_saldo": nuevo_saldo_final, # Aquí saldrán los $3,150
            "cliente": sujeto,
            "fecha": abono.fecha_pago.strftime("%d/%m/%Y"),
            "hora": timezone.localtime(timezone.now()).strftime("%H:%M:%S")
        }, status=status.HTTP_201_CREATED)


# ==============================
# CALENDARIO Y OTROS
# ==============================

class EstadisticasDinamicasView(APIView):
    def get(self, request):
        periodo = request.query_params.get('periodo', 'semana')
        hoy = timezone.now()
        if periodo == 'semana':
            inicio = hoy - timedelta(days=7)
            truncado = TruncDay('fecha_creacion')
            formato = "%a"
        elif periodo == 'mes':
            inicio = hoy - timedelta(days=30)
            truncado = TruncMonth('fecha_creacion')
            formato = "%b"
        else:
            inicio = hoy - timedelta(days=365)
            truncado = TruncMonth('fecha_creacion')
            formato = "%b %Y"

        datos = Prestamo.objects.filter(fecha_creacion__gte=inicio).annotate(fecha_truncada=truncado).values('fecha_truncada').annotate(
            total_capital=Sum('monto_capital'), 
            total_interes=Sum('monto_total_pagar') - Sum('monto_capital')
        ).order_by('fecha_truncada')

        return Response([{"name": d['fecha_truncada'].strftime(formato), "capital": float(d['total_capital'] or 0), "interes": float(d['total_interes'] or 0)} for d in datos])

class CalendarioPagosView(APIView):
    def get(self, request):
        try:
            # 1. Configuración de Zona Horaria México
            mexico_tz = pytz.timezone('America/Mexico_City')
            hoy = timezone.now().astimezone(mexico_tz).date()
            
            
            # 2. Obtener parámetros de la URL
            mes = int(request.query_params.get("mes", hoy.month))
            anio = int(request.query_params.get("anio", hoy.year))

            proyecciones = []
            # Traemos préstamos activos con sus relaciones
            prestamos = Prestamo.objects.filter(activo=True).select_related("cliente", "grupo")

            for p in prestamos:
                # Convertimos la fecha de inicio a la zona horaria de México
                fecha_base = p.fecha_inicio
                if hasattr(fecha_base, 'astimezone'):
                    fecha_base = fecha_base.astimezone(mexico_tz).date()

                for i in range(1, p.cuotas + 1):
                    # Calcular días según modalidad
                    if p.modalidad == "S":
                        fecha_pago = fecha_base + timedelta(days=7 * i)
                    elif p.modalidad == "Q":
                        fecha_pago = fecha_base + timedelta(days=15 * i)
                    else:
                        fecha_pago = fecha_base + timedelta(days=30 * i)

                    # Si cae en Domingo, se pasa al Lunes (Regla Alexander)
                    if fecha_pago.weekday() == 6:
                        fecha_pago += timedelta(days=1)

                    # Solo agregamos si coincide con el mes y año que Alexander está viendo
                    if fecha_pago.month == mes and fecha_pago.year == anio:
                        # Verificar si ya existe un abono para esta cuota específica
                        ya_pagado = p.abonos.filter(semana_numero=i).exists()
                        tiene_mora = p.penalizaciones.filter(activa=True).exists()
                        
                        nombre_sujeto = p.cliente.nombre if p.cliente else (p.grupo.nombre_grupo if p.grupo else "N/A")
                        id_sujeto = p.cliente.id if p.cliente else (p.grupo.id if p.grupo else 0)
                        if p.grupo:
                            telefono_contacto = getattr(p, 'telefono_aval', "") # Buscamos en el préstamo
                        else:
                            telefono_contacto = p.cliente.telefono if p.cliente else ""

                        proyecciones.append({
                            "id": f"{p.id}-{i}",
                            "cliente": nombre_sujeto,
                            "idCliente": id_sujeto,
                            "fecha": fecha_pago.strftime("%Y-%m-%d"),
                            "monto": round(p.monto_total_pagar / p.cuotas, 2),
                            "estatus": "pagado" if ya_pagado else ("vencido" if fecha_pago < hoy else "pendiente"),
                            "con_penalizacion": tiene_mora,
                            "tel": telefono_contacto
                        })
            
            return Response(proyecciones)

        except Exception as e:
            # Esto nos dirá en los logs de Railway exactamente qué rompió
            print(f"ERROR EN CALENDARIO: {str(e)}")
            return Response({"error": "Error interno al generar calendario"}, status=500)
@api_view(['POST'])
@permission_classes([IsAdminUser])
def condonar_mora(request, pk):
    try:
        penalizacion = Penalizacion.objects.get(pk=pk)
        motivo = request.data.get('motivo')
        
        if not motivo or len(motivo) < 10: 
            return Response({"error": "Motivo inválido (mínimo 10 caracteres)"}, status=400)
        
        if penalizacion.activa:
            # 1. Obtener el préstamo asociado
            prestamo = penalizacion.prestamo
            
            # 2. RESTAR el monto de la mora del total a pagar del préstamo
            # Esto es lo que faltaba para que el abono baje a $600
            prestamo.monto_total_pagar -= penalizacion.monto_penalizado
            prestamo.save()
            
            # 3. Desactivar la penalización
            penalizacion.activa = False
            penalizacion.motivo_condonacion = motivo
            penalizacion.save()
            
            registrar_log(
                request.user, 
                "CONDONACION_MORA", 
                f"Condonados ${penalizacion.monto_penalizado} al préstamo #{prestamo.id}. Nuevo total: ${prestamo.monto_total_pagar}"
            )
            
            return Response({
                "message": "Condonada con éxito y saldo del préstamo actualizado",
                "nuevo_total_prestamo": prestamo.monto_total_pagar
            })
            
        return Response({"message": "Esta penalización ya no estaba activa"}, status=400)
    except Exception as e: 
        return Response({"error": str(e)}, status=500)

@api_view(['GET', 'POST'])
def obtener_proximo_folio(request):
    contador, _ = ContadorFolio.objects.get_or_create(id=1, defaults={'numero_actual': 1})
    if request.method == 'POST':
        folio = contador.numero_actual
        contador.numero_actual += 1
        contador.save()
        return Response({'folio': folio})
    return Response({'proximo_folio': contador.numero_actual})


# ==============================
# DIRECTORIO HÍBRIDO (CORREGIDO)
# ==============================

@api_view(['GET'])
def directorio_hibrido(request):
    search = request.query_params.get('search', '').strip().lower()
    clientes = Cliente.objects.all()
    grupos = Grupo.objects.all()
    
    
    if search:
        filtro_clientes = Q(nombre__icontains=search)
        filtro_grupos = Q(nombre_grupo__icontains=search)
        if search.isdigit():
            search_id = int(search)
            filtro_clientes |= Q(id=search_id)
            filtro_grupos |= Q(id=search_id)
        clientes = clientes.filter(filtro_clientes)
        grupos = grupos.filter(filtro_grupos)

    data_final = []

    # --- PROCESAR CLIENTES ---
    for c in clientes:
        c.es_grupo = False
        p_ind = Prestamo.objects.filter(cliente=c, activo=True).first()
        
        # 🔥 Detectar si es integrante de un grupo con deuda
        # Usamos select_related o prefetch para obtener el conteo de integrantes
        p_grupal = Prestamo.objects.filter(grupo__integrantes=c, activo=True).first()
        
        # Prioridad: Si tiene préstamo individual, manda ese. Si no, el grupal.
        p = p_ind or p_grupal
        
        if p:
            total_abonado_calc = p.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
            saldo_total_prestamo = float(p.monto_total_pagar) - float(total_abonado_calc)
            multas = Penalizacion.objects.filter(prestamo=p, activa=True)
            total_m = multas.aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0
            c.monto_total_pagar = float(p.monto_total_pagar) # Valor total original
            c.cuotas = p.cuotas
            # Suma de capital pendiente + multas
            deuda_global_del_folio = saldo_total_prestamo 

            # 🔥 LÓGICA DE DIVISIÓN PARA CLIENTES
            if p_grupal and not p_ind:
                # Si el bloqueo viene por grupo, dividimos la deuda entre los miembros
                num_miembros = p_grupal.grupo.integrantes.count() or 1
                c.saldo_actual = deuda_global_del_folio / num_miembros
            else:
                # Si es préstamo individual, debe el 100%
                c.saldo_actual = deuda_global_del_folio

            c.tiene_prestamo_activo = True
            c.ultimo_prestamo_id = p.id
            c.total_penalizaciones = float(total_m)
            c.penalizaciones = [{"monto_penalizado": float(m.monto_penalizado), "activa": m.activa} for m in multas]
        else:
            c.tiene_prestamo_activo = False
            c.saldo_actual = 0
            c.total_penalizaciones = 0
            c.penalizaciones = []
            
        data_final.append(c)

    # --- PROCESAR GRUPOS ---
    for g in grupos:
        p = Prestamo.objects.filter(grupo=g, activo=True).first()
        g.es_grupo = True
        g.nombre = g.nombre_grupo
        if p:
            total_ab = p.abonos.aggregate(Sum('monto'))['monto__sum'] or 0
            saldo_cap_g = float(p.monto_total_pagar) - float(total_ab)
            multas_g = Penalizacion.objects.filter(prestamo=p, activa=True)
            total_mg = multas_g.aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0
            g.monto_total_pagar = float(p.monto_total_pagar)
            g.cuotas = p.cuotas
            g.tiene_prestamo_activo = True
            g.ultimo_prestamo_id = p.id
            # 🔥 El grupo SIEMPRE muestra el total de la deuda
            g.saldo_actual = saldo_cap_g
            g.penalizaciones = [{"monto_penalizado": float(m.monto_penalizado), "activa": m.activa} for m in multas_g]
        else:
            g.tiene_prestamo_activo = False
            g.saldo_actual = 0
            g.penalizaciones = []
        data_final.append(g)

    data_final.sort(key=lambda x: x.id, reverse=True)
    serializer = DirectorioHibridoSerializer(data_final, many=True)
    return Response(serializer.data)

from django.db.models import Sum
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.utils import timezone
from datetime import timedelta
from .models import Prestamo, Penalizacion
import pytz

@api_view(['GET'])
def cartera_vencida_hibrida(request):
    # 1. Anclamos la vista a la hora de México
    mexico_tz = pytz.timezone('America/Mexico_City')
    hoy = timezone.now().astimezone(mexico_tz).date()
    data_cartera = []

    prestamos_activos = Prestamo.objects.filter(activo=True).select_related(
        'cliente', 'grupo'
    ).prefetch_related('abonos', 'penalizaciones')

    for p in prestamos_activos:
        try:
            atraso_detectado = False
            fecha_vencimiento_antigua = None
            
            # Normalizamos la fecha de inicio a México (crucial por el server en Indonesia)
            fecha_base = p.fecha_inicio.astimezone(mexico_tz).date()

            for i in range(1, p.cuotas + 1):
                if p.modalidad in ["Semanal", "S", "Semanal "]:
                    fv = fecha_base + timedelta(days=7 * i)
                elif p.modalidad in ["Quincenal", "Q", "Quincenal "]:
                    fv = fecha_base + timedelta(days=15 * i)
                else:
                    fv = fecha_base + timedelta(days=30 * i)

                if fv.weekday() == 6: fv += timedelta(days=1)

                # Usamos <= para que Alexander vea el aviso desde el primer minuto del vencimiento
                if fv < hoy:
                    pagado = p.abonos.filter(semana_numero=i).exists()
                    if not pagado:
                        atraso_detectado = True
                        fecha_vencimiento_antigua = fv
                        break 
            
            multas_activas = p.penalizaciones.filter(activa=True)
            total_multas = float(multas_activas.aggregate(Sum('monto_penalizado'))['monto_penalizado__sum'] or 0)

            if atraso_detectado or total_multas > 0:
                es_grupo = (p.tipo == 'G')
                nombre = p.grupo.nombre_grupo if (es_grupo and p.grupo) else (p.cliente.nombre if p.cliente else "N/A")
                
                # 🔥 CÁLCULO CORREGIDO PARA ALEXANDER:
                # 1. Obtenemos la cuota pactada (Luis: 3600 / 8 = 450)
                cuota_fija = float(p.monto_total_pagar) / float(p.cuotas if p.cuotas > 0 else 1)
                
                # 2. El monto vencido es: (Cuota * 1) + multas acumuladas
                # Luis: (450 * 1) + 45 = 495.00
                monto_vencido = round((cuota_fija if atraso_detectado else 0) + total_multas, 2)
                
                # Días de atraso
                dias = (hoy - fecha_vencimiento_antigua).days if fecha_vencimiento_antigua else 0

                data_cartera.append({
                    "id_prestamo": p.id,
                    "nombre_deudor": nombre,
                    "es_grupo": es_grupo,
                    "monto_vencido": monto_vencido, # <--- Ahora enviará 495.00
                    "dias_atraso": dias,
                    "fecha_vencimiento": fecha_vencimiento_antigua.strftime("%Y-%m-%d") if fecha_vencimiento_antigua else "Solo Multas",
                    "telefono": p.telefono_aval if es_grupo else (p.cliente.telefono if p.cliente else ""),
                    "total_penalizaciones": total_multas
                })

        except Exception as e:
            print(f"Error en préstamo {p.id}: {e}")

    data_cartera.sort(key=lambda x: x['dias_atraso'], reverse=True)
    return Response(data_cartera)

@api_view(['GET'])
def reporte_flujo_efectivo(request):
    periodo = request.query_params.get('periodo', 'diario') # diario, semanal, mensual, anual
    mexico_tz = pytz.timezone('America/Mexico_City')
    hoy = timezone.now().astimezone(mexico_tz).date()

    # Definir el inicio del rango
    if periodo == 'semanal':
        inicio = hoy - timedelta(days=hoy.weekday())
    elif periodo == 'mensual':
        inicio = hoy.replace(day=1)
    elif periodo == 'anual':
        inicio = hoy.replace(month=1, day=1)
    else:
        inicio = hoy

    # 1. EGRESOS (Dinero que salió: Capital prestado)
    egresos = Prestamo.objects.filter(
        fecha_creacion__date__gte=inicio, 
        fecha_creacion__date__lte=hoy
    ).aggregate(total=Sum('monto_capital'))['total'] or 0

    # 2. INGRESOS (Dinero que entró: Abonos + Penalizaciones)
    ingresos_abonos = Abono.objects.filter(
        fecha_pago__gte=inicio, 
        fecha_pago__lte=hoy
    ).aggregate(total=Sum('monto'))['total'] or 0

    ingresos_moras = Penalizacion.objects.filter(
        fecha_aplicacion__gte=inicio, 
        fecha_aplicacion__lte=hoy,
        activa=False # Asumimos que si no está activa es porque se pagó
    ).aggregate(total=Sum('monto_penalizado'))['total'] or 0

    total_ingresos = float(ingresos_abonos) + float(ingresos_moras)

    return Response({
        "periodo": periodo,
        "desde": inicio,
        "hasta": hoy,
        "colocacion_capital": float(egresos),
        "recuperacion_total": total_ingresos,
        "balance_neto": total_ingresos - float(egresos)
    })
# views.py
