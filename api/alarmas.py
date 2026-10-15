"""Alarmas de estacionamiento incorrecto (ESP32 <-> Django <-> Front, por polling).

Tabla nueva: alarmasnuevo. No toca ninguna tabla ni lógica existente
(el flujo APAGAR_ALARMA del autómata, en backend_logic.py, sigue igual).
"""
from django.db import connection, transaction
from django.utils import timezone

from .errors import ErrorParqueo


def activar(placa, cajon, motivo=None):
    if not isinstance(placa, str) or not placa.strip():
        raise ErrorParqueo('Falta placa.', 400)
    placa = placa.strip().upper()
    try:
        cajon = int(cajon)
    except (TypeError, ValueError):
        raise ErrorParqueo('cajon debe ser un número.', 400)
    motivo = (motivo or 'ESTACIONAMIENTO_INCORRECTO')
    if not isinstance(motivo, str) or not motivo.strip():
        raise ErrorParqueo('motivo inválido.', 400)
    motivo = motivo.strip().upper()[:40]

    with transaction.atomic():
        with connection.cursor() as c:
            # Idempotente: si ya hay una alarma ACTIVA para esta placa, no duplica la fila
            # (evita que el ESP32 llene la tabla si reintenta el POST varias veces).
            c.execute("""SELECT id, cajon, motivo, fecha_activacion, estado
                FROM alarmasnuevo WHERE placa=%s AND estado='ACTIVA'
                ORDER BY id DESC LIMIT 1 FOR UPDATE""", [placa])
            existente = c.fetchone()
            if existente:
                return {'ok': True, 'nueva': False, 'alarma_id': existente[0], 'placa': placa,
                        'cajon': existente[1], 'motivo': existente[2],
                        'fecha_activacion': existente[3].isoformat(), 'estado': existente[4]}
            ahora = timezone.now()
            c.execute("""INSERT INTO alarmasnuevo (placa, cajon, motivo, fecha_activacion, estado)
                VALUES (%s,%s,%s,%s,'ACTIVA')""", [placa, cajon, motivo, ahora])
            aid = c.lastrowid
    return {'ok': True, 'nueva': True, 'alarma_id': aid, 'placa': placa, 'cajon': cajon,
            'motivo': motivo, 'fecha_activacion': ahora.isoformat(), 'estado': 'ACTIVA'}


def silenciar(placa):
    if not isinstance(placa, str) or not placa.strip():
        raise ErrorParqueo('Falta placa.', 400)
    placa = placa.strip().upper()
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("""SELECT id FROM alarmasnuevo WHERE placa=%s AND estado='ACTIVA'
                ORDER BY id DESC LIMIT 1 FOR UPDATE""", [placa])
            fila = c.fetchone()
            if not fila:
                raise ErrorParqueo('No hay alarma activa para esa placa.', 404)
            ahora = timezone.now()
            c.execute("""UPDATE alarmasnuevo SET estado='SILENCIADA', fecha_silenciada=%s
                WHERE id=%s""", [ahora, fila[0]])
    return {'ok': True, 'alarma_id': fila[0], 'placa': placa, 'estado': 'SILENCIADA',
            'fecha_silenciada': ahora.isoformat()}


def estado_de(placa):
    if not isinstance(placa, str) or not placa.strip():
        raise ErrorParqueo('Falta parámetro placa.', 400)
    placa = placa.strip().upper()
    with connection.cursor() as c:
        c.execute("""SELECT id, estado, fecha_activacion, fecha_silenciada
            FROM alarmasnuevo WHERE placa=%s ORDER BY id DESC LIMIT 1""", [placa])
        fila = c.fetchone()
    if not fila:
        # El ESP32 usa esto para saber que ya no debe sonar / no hay nada que rastrear.
        return {'ok': True, 'placa': placa, 'estado': 'SIN_ALARMA'}
    return {'ok': True, 'placa': placa, 'alarma_id': fila[0], 'estado': fila[1],
            'fecha_activacion': fila[2].isoformat(),
            'fecha_silenciada': fila[3].isoformat() if fila[3] else None}


def listar(estado=None):
    sql = """SELECT id, placa, cajon, motivo, fecha_activacion, estado, fecha_silenciada
        FROM alarmasnuevo"""
    params = []
    if estado:
        sql += " WHERE estado=%s"
        params.append(estado.strip().upper())
    sql += " ORDER BY fecha_activacion DESC"
    with connection.cursor() as c:
        c.execute(sql, params)
        cols = [x[0] for x in c.description]
        filas = []
        for fila in c.fetchall():
            d = dict(zip(cols, fila))
            d['fecha_activacion'] = d['fecha_activacion'].isoformat()
            d['fecha_silenciada'] = d['fecha_silenciada'].isoformat() if d['fecha_silenciada'] else None
            filas.append(d)
    return filas
