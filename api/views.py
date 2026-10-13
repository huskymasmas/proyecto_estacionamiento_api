import json, os, secrets
from datetime import datetime, timedelta
from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from . import backend_logic
from .errors import ErrorParqueo
from .lenguaje.lexer_parqueo import ErrorLexico
from .lenguaje.parser_parqueo import ErrorSintactico, interpretar_comando
from .rfid_commands import ejecutar_comando, confirmar_pago, crear_solicitud_manual


def leer(request):
    try:
        d = json.loads(request.body or b'{}')
        if not isinstance(d,dict): raise ValueError()
        return d
    except (ValueError,TypeError): raise ErrorParqueo('JSON inválido.',400)


def error(e):
    return JsonResponse({'ok':False, 'abrir_barrera':False, 'error':e.mensaje},status=e.status)


def rows(sql, params=()):
    with connection.cursor() as c:
        c.execute(sql,list(params))
        cols=[x[0] for x in c.description]
        return [dict(zip(cols,[v.isoformat() if hasattr(v,'isoformat') else float(v) if hasattr(v,'quantize') else v for v in fila])) for fila in c.fetchall()]


@require_GET
def espacios(request):
    return JsonResponse(rows("""SELECT e.codigo,e.categoria,e.estado,v.placa
        FROM espaciosnuevos e
        LEFT JOIN registros_accesonuevos r ON r.espacio_id=e.id AND r.estado='ACTIVO'
        LEFT JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
        ORDER BY e.codigo"""),safe=False)


@require_GET
def espacios_ocupados(request):
    return JsonResponse(rows("""SELECT r.id AS registro_id,v.placa,e.categoria AS tipo,
        e.codigo AS espacio,r.fecha_entrada,
        TIMESTAMPDIFF(MINUTE,r.fecha_entrada,NOW()) AS minutos_transcurridos,
        r.monto_total
        FROM registros_accesonuevos r
        JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
        JOIN espaciosnuevos e ON e.id=r.espacio_id
        WHERE r.estado='ACTIVO' ORDER BY r.fecha_entrada DESC"""),safe=False)


@require_GET
def historial(request):
    try: limit=max(1,min(1000,int(request.GET.get('limit',100))))
    except ValueError: return error(ErrorParqueo('limit inválido',400))
    cond=["r.estado IN ('FINALIZADO','CANCELADO')"]; params=[]
    if request.GET.get('placa'):
        cond.append('v.placa LIKE %s');params.append('%'+request.GET['placa']+'%')
    for param,operador in [('desde','>='),('hasta','<')]:
        if request.GET.get(param):
            try: fecha=datetime.strptime(request.GET[param],'%Y-%m-%d')
            except ValueError: return error(ErrorParqueo('Fecha inválida YYYY-MM-DD.',400))
            if param=='hasta': fecha+=timedelta(days=1)
            cond.append('r.fecha_entrada '+operador+' %s'); params.append(fecha)
    return JsonResponse(rows(f"""SELECT r.id AS registro_id,v.placa,e.codigo AS espacio,
        r.fecha_entrada,r.fecha_salida,r.monto_total,r.estado
        FROM registros_accesonuevos r JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
        JOIN espaciosnuevos e ON e.id=r.espacio_id
        WHERE {' AND '.join(cond)} ORDER BY r.fecha_entrada DESC LIMIT {limit}""",params),safe=False)


@require_POST
def comando(request):
    try:
        d=leer(request); texto=d.get('comando')
        if not isinstance(texto,str): raise ErrorParqueo('Falta comando.',400)
        try: parsed=interpretar_comando(texto)
        except ErrorLexico as e:return JsonResponse({'ok':False,'abrir_barrera':False,'etapa':'lexico','error':str(e)},status=400)
        except ErrorSintactico as e:return JsonResponse({'ok':False,'abrir_barrera':False,'etapa':'sintactico','error':str(e)},status=400)
        return JsonResponse({'ok':True,'comando':texto,'instruccion':parsed,
                             **backend_logic.ejecutar(parsed,d.get('usuario_id'),d.get('espacio'))})
    except ErrorParqueo as e:return error(e)


@require_POST
def rfid_comando(request):
    try:
        d=leer(request)
        if set(d)!={'comando'}: raise ErrorParqueo('Envía únicamente comando.',400)
        return JsonResponse(ejecutar_comando(d['comando']))
    except ErrorParqueo as e:return error(e)


@require_POST
def rfid(request):
    return error(ErrorParqueo('Usa /api/rfid/comando con ASIGNAR(...) o SALIDA(...).',400))






@require_POST
def pago_confirmar(request):
    try:
        d=leer(request)
        if set(d)!={'placa'}: raise ErrorParqueo('Envía únicamente placa.',400)
        return JsonResponse(confirmar_pago(d['placa']))
    except ErrorParqueo as e:return error(e)
