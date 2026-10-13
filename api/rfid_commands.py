"""Operaciones RFID sobre las cinco tablas MySQL EXISTENTES (sin autómatas)."""
import re
from django.db import connection, transaction
from .errors import ErrorParqueo

# Placa -> (cajón exacto, tipo en vehiculosnuevos)
FIJOS = {
    'P101CMP': (1, 'compacto'),
    'P102CMP': (2, 'compacto'),
    'P401CRG': (4, 'carga'),
    'P501RSV': (5, 'reserva'),
    'P601GRD': (6, 'grande'),
    'M701MOT': (7, 'moto'),
}
CATEGORIAS = {1:'compacto',2:'compacto',3:'manual',4:'carga',5:'reserva',6:'grande',7:'moto'}
COMANDO = re.compile(
    r'^(ASIGNAR|SALIDA)\((P101CMP|P102CMP|P401CRG|P501RSV|P601GRD|M701MOT|MANUAL)\)$'
)
PLACA_WEB = re.compile(r'^[A-Z0-9]{6,20}$')


def fallo(texto, status=409):
    raise ErrorParqueo(texto, status)


def buscar_espacio(cursor, numero):
    # BLOQUEAR antes de verificar ocupación; evita asignaciones simultáneas.
    cursor.execute("SELECT id, categoria, estado FROM espaciosnuevos WHERE codigo=%s FOR UPDATE", [f'CAJON_{numero}'])
    r = cursor.fetchone()
    if r is None:
        fallo(f'No existe CAJON_{numero} en espaciosnuevos.', 500)
    if r[1].lower() != CATEGORIAS[numero]:
        fallo(f'Categoría de CAJON_{numero} incorrecta: {r[1]}.', 409)
    return r[0], r[2]


def estancia_cajon(cursor, espacio_id):
    cursor.execute("""SELECT r.id, r.vehiculo_id, v.placa, r.fecha_entrada
        FROM registros_accesonuevos r
        JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
        WHERE r.espacio_id=%s AND r.estado='ACTIVO' LIMIT 1 FOR UPDATE""", [espacio_id])
    return cursor.fetchone()


def vehiculo_fijo(cursor, placa):
    numero, tipo = FIJOS[placa]
    cursor.execute('SELECT id, tipo_vehiculo FROM vehiculosnuevos WHERE placa=%s FOR UPDATE', [placa])
    v = cursor.fetchone()
    if not v:
        fallo(f'El vehículo {placa} no está registrado.', 404)
    if v[1].lower() != tipo:
        fallo(f'El vehículo {placa} debe ser de tipo {tipo}.', 403)
    return v[0], numero


def validar_disponibilidad(cursor, espacio_id, estado, vehiculo_id, numero):
    cursor.execute("SELECT id FROM registros_accesonuevos WHERE vehiculo_id=%s AND estado='ACTIVO' LIMIT 1 FOR UPDATE", [vehiculo_id])
    if cursor.fetchone():
        fallo('Ya está dentro')
    if estado != 'LIBRE' or estancia_cajon(cursor, espacio_id):
        fallo(f'El cajón {numero} está ocupado o no disponible.')


def asignar(cursor, clave):
    if clave == 'MANUAL':
        num = 3
        eid, estado = buscar_espacio(cursor, num)
        if estado != 'LIBRE' or estancia_cajon(cursor, eid):
            fallo('Cajón 3 Manual ocupado.')
        cursor.execute("""SELECT id, placa FROM solicitudes_manualnuevo
            WHERE estado='PENDIENTE' AND fecha_creacion >= CURDATE()
              AND fecha_creacion < CURDATE() + INTERVAL 1 DAY
            ORDER BY fecha_creacion, id LIMIT 2 FOR UPDATE""")
        solicitudes = cursor.fetchall()
        if not solicitudes:
            fallo('No hay solicitud Manual pendiente de hoy.', 404)
        if len(solicitudes) > 1:
            fallo('Hay varias solicitudes Manual pendientes; selección ambigua.')
        solicitud_id, placa = solicitudes[0]
        if placa in FIJOS or placa == 'MANUAL':
            fallo('La solicitud Manual contiene una placa reservada.', 403)
        cursor.execute('SELECT id FROM vehiculosnuevos WHERE placa=%s FOR UPDATE', [placa])
        vehiculo = cursor.fetchone()
        if not vehiculo:
            fallo(f'La placa dinámica {placa} no está registrada en vehiculosnuevos.', 404)
        vid = vehiculo[0]
    else:
        vid, num = vehiculo_fijo(cursor, clave)
        placa = clave
        eid, estado = buscar_espacio(cursor, num)
        solicitud_id = None
    validar_disponibilidad(cursor, eid, estado, vid, num)
    cursor.execute("UPDATE espaciosnuevos SET estado='OCUPADO' WHERE id=%s AND estado='LIBRE'", [eid])
    if cursor.rowcount != 1:
        fallo('No se pudo reservar el cajón.')
    cursor.execute("""INSERT INTO registros_accesonuevos
        (vehiculo_id, espacio_id, fecha_entrada, estado, monto_total)
        VALUES (%s,%s,NOW(),'ACTIVO',0.00)""", [vid, eid])
    rid = cursor.lastrowid
    if solicitud_id is not None:
        cursor.execute("UPDATE solicitudes_manualnuevo SET estado='ASIGNADO' WHERE id=%s AND estado='PENDIENTE'", [solicitud_id])
        if cursor.rowcount != 1:
            fallo('La solicitud Manual ya fue asignada.')
    return {'ok':True, 'accion':'ASIGNAR', 'placa':placa, 'cajon':num,
            'registro_id':rid, 'abrir_barrera':True, 'mensaje':'Entrada autorizada'}


def salida(cursor, clave):
    if clave == 'MANUAL':
        num, vid = 3, None
    else:
        vid, num = vehiculo_fijo(cursor, clave)
    eid, estado = buscar_espacio(cursor, num)
    activa = estancia_cajon(cursor, eid)
    if activa is None:
        fallo(f'No hay vehículo activo en el cajón {num}.')
    rid, vid_real, placa, fecha_entrada = activa
    if vid is not None and (vid != vid_real or placa != clave):
        fallo('La placa no corresponde al vehículo estacionado.',403)
    # Pago posterior a la entrada y no consumido. Una autorización no habilita otra estancia.
    cursor.execute("""SELECT id FROM autorizaciones_salidanuevo
        WHERE placa=%s AND estado='AUTORIZADO' AND fecha_pago >= %s
        ORDER BY fecha_pago DESC, id DESC LIMIT 1 FOR UPDATE""", [placa, fecha_entrada])
    permiso = cursor.fetchone()
    if not permiso:
        fallo('Salida denegada: pago no autorizado.',403)
    if estado != 'OCUPADO':
        fallo('Inconsistencia: la estancia está activa, pero el cajón no está OCUPADO.')
    cursor.execute("""UPDATE registros_accesonuevos SET estado='FINALIZADO', fecha_salida=NOW()
        WHERE id=%s AND estado='ACTIVO'""", [rid])
    if cursor.rowcount != 1:
        fallo('No se pudo finalizar la estancia.')
    cursor.execute("UPDATE espaciosnuevos SET estado='LIBRE' WHERE id=%s AND estado='OCUPADO'", [eid])
    if cursor.rowcount != 1:
        fallo('No se pudo liberar el cajón.')
    cursor.execute("UPDATE autorizaciones_salidanuevo SET estado='CONSUMIDO' WHERE id=%s AND estado='AUTORIZADO'", [permiso[0]])
    if cursor.rowcount != 1:
        fallo('No se pudo consumir la autorización de salida.')
    if num == 3:
        cursor.execute("""UPDATE solicitudes_manualnuevo SET estado='FINALIZADO'
            WHERE placa=%s AND estado='ASIGNADO'""", [placa])
    return {'ok':True, 'accion':'SALIDA', 'placa':placa, 'cajon':num,
            'registro_id':rid, 'abrir_barrera':True, 'mensaje':'Salida autorizada'}


def ejecutar_comando(texto):
    if not isinstance(texto,str):
        fallo('comando debe ser texto.',400)
    match = COMANDO.fullmatch(texto.strip().upper())
    if not match:
        fallo('Comando RFID inválido. Usa ASIGNAR(PLACA), ASIGNAR(MANUAL), SALIDA(PLACA) o SALIDA(MANUAL).',400)
    with transaction.atomic():
        with connection.cursor() as c:
            return asignar(c,match[2]) if match[1]=='ASIGNAR' else salida(c,match[2])


def crear_solicitud_manual(placa):
    """Web: deja una única solicitud pendiente; crea vehículo dinámico de tipo indicado en la Web.
    Requiere que el vehículo ya esté registrado; esta ruta no inventa su tipo.
    """
    if not isinstance(placa,str): fallo('Placa inválida.',400)
    placa=placa.strip().upper()
    if not PLACA_WEB.fullmatch(placa) or placa in FIJOS or placa=='MANUAL':
        fallo('Placa dinámica inválida o reservada.',400)
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute('SELECT id FROM vehiculosnuevos WHERE placa=%s FOR UPDATE',[placa])
            if not c.fetchone(): fallo('Registra primero el vehículo dinámico desde la Web.',404)
            c.execute("SELECT id FROM registros_accesonuevos r JOIN vehiculosnuevos v ON v.id=r.vehiculo_id WHERE v.placa=%s AND r.estado='ACTIVO' LIMIT 1",[placa])
            if c.fetchone(): fallo('Este vehículo ya está adentro.')
            eid, estado = buscar_espacio(c,3)
            if estado!='LIBRE' or estancia_cajon(c,eid): fallo('Cajón Manual ocupado.')
            c.execute("SELECT id FROM solicitudes_manualnuevo WHERE estado='PENDIENTE' LIMIT 1 FOR UPDATE")
            if c.fetchone(): fallo('Ya hay otra solicitud Manual pendiente.')
            c.execute("INSERT INTO solicitudes_manualnuevo (placa,fecha_creacion,estado) VALUES (%s,NOW(),'PENDIENTE')",[placa])
            sid=c.lastrowid
    return {'ok':True,'solicitud_id':sid,'placa':placa,'estado':'PENDIENTE','cajon':3}


def confirmar_pago(placa):
    """Solo invocar DESPUÉS de que la Web haya confirmado el pago real."""
    if not isinstance(placa,str): fallo('Placa inválida.',400)
    placa=placa.strip().upper()
    if not PLACA_WEB.fullmatch(placa): fallo('Placa inválida.',400)
    with transaction.atomic():
        with connection.cursor() as c:
            c.execute("""SELECT r.id,r.fecha_entrada FROM registros_accesonuevos r
                JOIN vehiculosnuevos v ON v.id=r.vehiculo_id
                WHERE v.placa=%s AND r.estado='ACTIVO' LIMIT 1 FOR UPDATE""",[placa])
            activa=c.fetchone()
            if not activa: fallo('No hay estancia activa para autorizar salida.',404)
            c.execute("""SELECT id FROM autorizaciones_salidanuevo WHERE placa=%s
                AND estado='AUTORIZADO' AND fecha_pago >= %s LIMIT 1 FOR UPDATE""", [placa,activa[1]])
            if c.fetchone(): fallo('Esta estancia ya tiene salida autorizada.')
            c.execute("""INSERT INTO autorizaciones_salidanuevo (placa,fecha_pago,estado)
                VALUES (%s,NOW(),'AUTORIZADO')""",[placa])
            aid=c.lastrowid
    return {'ok':True,'placa':placa,'autorizacion_id':aid,'estado':'AUTORIZADO'}
