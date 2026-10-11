"""Vistas con consultas SQL directas (SQL) a las tablas que ya existen en
estacionamiento_db. No hay modelos ni migraciones."""
import json
from datetime import datetime, timedelta

from django.db import connection
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import backend_logic
from .lenguaje.lexer_parqueo import ErrorLexico
from .lenguaje.parser_parqueo import ErrorSintactico, interpretar_comando

# Horas cobradas: se redondea hacia arriba, mínimo 1 hora
HORAS_COBRADAS = """
    CASE WHEN TIMESTAMPDIFF(MINUTE, r.fecha_entrada, NOW()) <= 0 THEN 1
         ELSE CEILING(TIMESTAMPDIFF(MINUTE, r.fecha_entrada, NOW()) / 60.0) END
"""


def fetch_all(sql, params=None):
    """Ejecuta un SELECT y devuelve una lista de dicts serializable a JSON."""
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columnas = [c[0] for c in cursor.description]
        filas = cursor.fetchall()

    resultado = []
    for fila in filas:
        item = {}
        for col, val in zip(columnas, fila):
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif hasattr(val, "quantize"):  # Decimal
                val = float(val)
            item[col] = val
        resultado.append(item)
    return resultado


@require_GET
def espacios(request):
    """Todos los espacios con su estado (para pintar el mapa)."""
    data = fetch_all("""
        SELECT e.codigo, e.estado, e.ubicacion,
               c.codigo_categoria AS tipo, c.tarifa_por_hora,
               v.placa
        FROM espacios e
        JOIN catalogo_espacios c ON c.id = e.catalogo_espacio_id
        LEFT JOIN registros_acceso r ON r.espacio_id = e.id AND r.estado = 'ACTIVO'
        LEFT JOIN vehiculos v ON v.id = r.vehiculo_id
        ORDER BY e.codigo
    """)
    return JsonResponse(data, safe=False)


@require_GET
def espacios_ocupados(request):
    """Solo los espacios que se están usando ahora (registro ACTIVO)."""
    data = fetch_all(f"""
        SELECT r.id AS registro_id,
               v.placa,
               c.codigo_categoria AS tipo,
               e.codigo AS espacio,
               e.ubicacion,
               r.fecha_entrada,
               TIMESTAMPDIFF(MINUTE, r.fecha_entrada, NOW()) AS minutos_transcurridos,
               c.tarifa_por_hora,
               ({HORAS_COBRADAS}) * c.tarifa_por_hora AS monto_estimado,
               'PENDIENTE' AS pago
        FROM registros_acceso r
        JOIN vehiculos v ON v.id = r.vehiculo_id
        JOIN espacios e ON e.id = r.espacio_id
        JOIN catalogo_espacios c ON c.id = e.catalogo_espacio_id
        WHERE r.estado = 'ACTIVO'
        ORDER BY r.fecha_entrada DESC
    """)
    return JsonResponse(data, safe=False)


@require_GET
def historial(request):
    """Registros FINALIZADO / CANCELADO.
    Query params opcionales: placa, desde (YYYY-MM-DD), hasta (YYYY-MM-DD), limit (def. 100)."""
    filtros = ["r.estado IN ('FINALIZADO', 'CANCELADO')"]
    params = []

    try:
        limit = min(int(request.GET.get("limit", 100)), 1000)
        desde = request.GET.get("desde")
        hasta = request.GET.get("hasta")
        if desde:
            filtros.append("r.fecha_entrada >= %s")
            params.append(datetime.strptime(desde, "%Y-%m-%d"))
        if hasta:  # incluye todo el día "hasta"
            filtros.append("r.fecha_entrada < %s")
            params.append(datetime.strptime(hasta, "%Y-%m-%d") + timedelta(days=1))
    except ValueError:
        return JsonResponse(
            {"error": "Parámetros inválidos. Usa fechas YYYY-MM-DD y limit numérico."},
            status=400,
        )

    placa = request.GET.get("placa")
    if placa:
        filtros.append("v.placa LIKE %s")
        params.append(f"%{placa}%")

    # limit ya es un int validado, por eso se puede interpolar en LIMIT
    data = fetch_all(f"""
        SELECT r.id AS registro_id,
               v.placa,
               c.codigo_categoria AS tipo,
               e.codigo AS espacio,
               r.fecha_entrada,
               r.fecha_salida,
               TIMESTAMPDIFF(MINUTE, r.fecha_entrada, r.fecha_salida) AS minutos_totales,
               r.monto_total,
               r.estado,
               CASE r.estado WHEN 'FINALIZADO' THEN 'PAGADO' ELSE 'CANCELADO' END AS pago,
               u.nombre_completo AS atendido_por
        FROM registros_acceso r
        JOIN vehiculos v ON v.id = r.vehiculo_id
        JOIN espacios e ON e.id = r.espacio_id
        JOIN catalogo_espacios c ON c.id = e.catalogo_espacio_id
        LEFT JOIN usuarios u ON u.id = r.usuario_id
        WHERE {' AND '.join(filtros)}
        ORDER BY r.fecha_salida DESC, r.fecha_entrada DESC
        LIMIT {limit}
    """, params)
    return JsonResponse(data, safe=False)


@require_POST
def comando(request):
    """Recibe un comando del lenguaje del parqueo, lo pasa por el autómata
    (lexer + parser) y lo traduce a operaciones en la base de datos.

    Body JSON: {"comando": "REGISTRAR(compacto,ABC123)", "usuario_id": 2}   (usuario_id es opcional)
    """
    try:
        body = json.loads(request.body or b"{}")
    except ValueError:
        return JsonResponse({"ok": False, "error": "El body debe ser JSON válido."}, status=400)

    texto = body.get("comando") if isinstance(body, dict) else None
    if not isinstance(texto, str) or not texto.strip():
        return JsonResponse({"ok": False, "error": 'Falta el campo "comando".'}, status=400)

    # 1) Autómata: análisis léxico y sintáctico
    try:
        instruccion = interpretar_comando(texto)
    except ErrorLexico as e:
        return JsonResponse({"ok": False, "etapa": "lexico", "error": str(e)}, status=400)
    except ErrorSintactico as e:
        return JsonResponse({"ok": False, "etapa": "sintactico", "error": str(e)}, status=400)

    # 2) Traducción a la base de datos
    try:
        resultado = backend_logic.ejecutar(instruccion, body.get("usuario_id"), body.get("espacio"))
    except backend_logic.ErrorParqueo as e:
        return JsonResponse({"ok": False, "etapa": "bd", "error": e.mensaje}, status=e.status)

    return JsonResponse(
        {"ok": True, "comando": texto, "instruccion": instruccion, **resultado}, status=200
    )
