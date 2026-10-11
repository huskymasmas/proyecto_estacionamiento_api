"""Traducción de comandos del autómata, manteniendo lexer/parser originales."""
from django.db import connection, transaction
from .rfid_commands import FIJOS, ejecutar_comando
from .errors import ErrorParqueo


def ejecutar(instruccion, usuario_id=None, espacio=None):
    accion = instruccion['accion']
    placa = instruccion.get('placa')
    if accion == 'REGISTRAR':
        tipo = instruccion['tipo'].lower()
        # Registro web/manual: guarda vehículo y crea solicitud pendiente
        # usando SOLO las tablas MySQL existentes. Las placas fijas no se alteran.
        if tipo == 'manual':
            from django.utils import timezone
            if placa in FIJOS or placa == 'MANUAL':
                raise ErrorParqueo('La placa está reservada para un cajón fijo.', 403)
            with transaction.atomic():
                with connection.cursor() as c:
                    c.execute('SELECT id FROM vehiculosnuevos WHERE placa=%s FOR UPDATE', [placa])
                    if c.fetchone():
                        raise ErrorParqueo('Vehículo ya registrado.', 409)
                    c.execute("SELECT id FROM solicitudes_manualnuevo WHERE estado='PENDIENTE' LIMIT 1 FOR UPDATE")
                    if c.fetchone():
                        raise ErrorParqueo('Ya existe una solicitud Manual pendiente.', 409)
                    c.execute("SELECT id, estado FROM espaciosnuevos WHERE codigo='CAJON_3' FOR UPDATE")
                    cajon = c.fetchone()
                    if not cajon or cajon[1] != 'LIBRE':
                        raise ErrorParqueo('El cajón Manual no está disponible.', 409)
                    # MySQL no tiene restricción ENUM en tipo_vehiculo según el esquema enviado.
                    c.execute('INSERT INTO vehiculosnuevos (placa,tipo_vehiculo) VALUES (%s,%s)', [placa, tipo])
                    vid = c.lastrowid
                    c.execute("INSERT INTO solicitudes_manualnuevo (placa,fecha_creacion,estado) VALUES (%s,%s,'PENDIENTE')", [placa, timezone.now()])
                    sid = c.lastrowid
            return {'resultado': {'vehiculo_id': vid, 'placa': placa,
                    'tipo_vehiculo': tipo, 'solicitud_id': sid, 'estado': 'PENDIENTE', 'cajon': 3},
                    'traduccion_bd': [{'operacion': 'INSERT', 'tabla': 'vehiculosnuevos'},
                                      {'operacion': 'INSERT', 'tabla': 'solicitudes_manualnuevo'}]}
        if placa not in FIJOS or FIJOS[placa][1] != tipo:
            raise ErrorParqueo('La placa no está autorizada para ese tipo de vehículo.',403)
        with transaction.atomic():
            with connection.cursor() as c:
                c.execute('SELECT id FROM vehiculosnuevos WHERE placa=%s FOR UPDATE',[placa])
                if c.fetchone(): raise ErrorParqueo('Vehículo ya registrado.',409)
                c.execute('INSERT INTO vehiculosnuevos (placa,tipo_vehiculo) VALUES (%s,%s)',[placa,tipo])
                vid = c.lastrowid
        return {'resultado':{'vehiculo_id':vid,'placa':placa,'tipo_vehiculo':tipo},
                'traduccion_bd':[{'operacion':'INSERT','tabla':'vehiculosnuevos'}]}
    if accion in ('ASIGNAR','LLEGADA'):
        if espacio is not None: raise ErrorParqueo('El cajón se determina por placa fija.',400)
        return {'resultado':ejecutar_comando(f'ASIGNAR({placa})')}
    if accion=='SALIDA': return {'resultado':ejecutar_comando(f'SALIDA({placa})')}
    if accion=='AUTORIZAR_SALIDA':
        return {'resultado':{'mensaje':'La autorización de pago debe confirmarse desde la Web, no desde el autómata.'}}
    if accion=='APAGAR_ALARMA':
        raise ErrorParqueo('La nueva base no incluye una tabla de alarmas; operación no disponible.',409)
    if accion=='CONSULTAR':
        with connection.cursor() as c:
            c.execute("""SELECT v.placa,e.codigo,r.fecha_entrada
                FROM registros_accesonuevos r
                JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
                JOIN espaciosnuevos e ON e.id=r.espacio_id WHERE r.estado='ACTIVO'""")
            filas=[{'placa':r[0], 'espacio':r[1], 'fecha_entrada':r[2].isoformat()} for r in c.fetchall()]
        return {'resultado':filas}
    raise ErrorParqueo('Acción no soportada.',400)
