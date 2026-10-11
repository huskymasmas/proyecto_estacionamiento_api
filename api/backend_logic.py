"""Traduce instrucciones ya validadas por el autómata a operaciones SQL.
No vuelve a validar la gramática: esa responsabilidad pertenece al lexer/parser.
"""
from decimal import Decimal
from django.db import connection, transaction


class ErrorParqueo(Exception):
    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


TIPO_A_VEHICULO = {
    "compacto": "AUTOMOVIL",
    "grande": "CAMIONETA",
    "moto": "MOTOCICLETA",
    "reserva": "AUTOMOVIL",
    "carga": "CAMION_CARGA",
}
VEHICULO_A_CATEGORIA = {
    "AUTOMOVIL": "COMPACTO", "CAMIONETA": "GRANDE",
    "MOTOCICLETA": "MOTO", "CAMION_CARGA": "CARGA",
}


def _vehiculo(cursor, placa):
    cursor.execute("SELECT id, placa, tipo_vehiculo FROM vehiculos WHERE placa = %s", [placa])
    row = cursor.fetchone()
    if not row:
        raise ErrorParqueo(f"El vehículo {placa} no está registrado.", 404)
    return row


def _registro_activo(cursor, vehiculo_id, bloquear=False):
    sql = "SELECT id, espacio_id, fecha_entrada FROM registros_acceso WHERE vehiculo_id=%s AND estado='ACTIVO' ORDER BY id DESC LIMIT 1"
    if bloquear:
        sql += " FOR UPDATE"
    cursor.execute(sql, [vehiculo_id])
    return cursor.fetchone()


def registrar_vehiculo(cursor, tipo, placa):
    if tipo not in TIPO_A_VEHICULO:
        raise ErrorParqueo("Tipo de vehículo no reconocido.")
    cursor.execute("SELECT 1 FROM vehiculos WHERE placa=%s", [placa])
    if cursor.fetchone():
        raise ErrorParqueo(f"La placa {placa} ya está registrada.", 409)
    tipo_bd = TIPO_A_VEHICULO[tipo]
    cursor.execute("INSERT INTO vehiculos (placa, tipo_vehiculo) VALUES (%s,%s)", [placa, tipo_bd])
    return {"resultado": {"vehiculo_id": cursor.lastrowid, "placa": placa, "tipo_vehiculo": tipo_bd},
            "traduccion_bd": [{"operacion": "INSERT", "tabla": "vehiculos", "datos": {"placa": placa, "tipo_vehiculo": tipo_bd}}]}


def llegada(cursor, placa, usuario_id=None):
    _, _, tipo_vehiculo = _vehiculo(cursor, placa)
    if _registro_activo(cursor, _vehiculo(cursor, placa)[0], bloquear=True):
        raise ErrorParqueo(f"El vehículo {placa} ya tiene una estancia activa.", 409)
    if tipo_vehiculo not in VEHICULO_A_CATEGORIA:
        raise ErrorParqueo(f"El tipo de vehículo {tipo_vehiculo} no tiene categoría de espacio configurada.", 409)
    if usuario_id is not None:
        cursor.execute("SELECT 1 FROM usuarios WHERE id=%s AND activo=1", [usuario_id])
        if not cursor.fetchone():
            raise ErrorParqueo(f"El usuario_id {usuario_id} no existe o está inactivo.", 400)
    categoria = VEHICULO_A_CATEGORIA[tipo_vehiculo]
    cursor.execute("""SELECT e.id,e.codigo,e.ubicacion FROM espacios e
        JOIN catalogo_espacios c ON c.id=e.catalogo_espacio_id
        WHERE c.codigo_categoria=%s AND c.activo=1 AND e.estado='LIBRE'
        ORDER BY e.id LIMIT 1 FOR UPDATE""", [categoria])
    espacio = cursor.fetchone()
    if not espacio:
        raise ErrorParqueo(f"No hay espacios libres para la categoría {categoria}.", 409)
    espacio_id, codigo, ubicacion = espacio
    vehiculo_id = _vehiculo(cursor, placa)[0]
    cursor.execute("INSERT INTO registros_acceso (vehiculo_id,espacio_id,usuario_id,estado,monto_total) VALUES (%s,%s,%s,'ACTIVO',0.00)",
                   [vehiculo_id, espacio_id, usuario_id])
    registro_id = cursor.lastrowid
    cursor.execute("UPDATE espacios SET estado='OCUPADO' WHERE id=%s", [espacio_id])
    cursor.execute("SELECT fecha_entrada FROM registros_acceso WHERE id=%s", [registro_id])
    fecha = cursor.fetchone()[0]
    return {"resultado": {"registro_id": registro_id, "placa": placa, "espacio": codigo,
            "ubicacion": ubicacion, "categoria": categoria,
            "fecha_entrada": fecha.isoformat() if hasattr(fecha, 'isoformat') else str(fecha), "estado": "ACTIVO"},
            "traduccion_bd": [
                {"operacion": "INSERT", "tabla": "registros_acceso", "datos": {"vehiculo_id": vehiculo_id, "espacio_id": espacio_id, "usuario_id": usuario_id, "estado": "ACTIVO", "monto_total": 0}},
                {"operacion": "UPDATE", "tabla": "espacios", "datos": {"id": espacio_id, "estado": "OCUPADO"}}]}


def autorizar_salida(cursor, placa):
    vehiculo_id, _, _ = _vehiculo(cursor, placa)
    registro = _registro_activo(cursor, vehiculo_id, bloquear=True)
    if not registro:
        raise ErrorParqueo(f"El vehículo {placa} no tiene una estancia activa que autorizar.", 409)
    # El esquema actual no muestra una columna para persistir la autorización.
    # La autorización es confirmada por el backend; SALIDA vuelve a comprobar el registro activo.
    return {"resultado": {"placa": placa, "registro_id": registro[0], "autorizada": True,
                          "mensaje": "Salida autorizada. Puede retirar el vehículo por el lector."},
            "traduccion_bd": [{"operacion": "SELECT", "tabla": "registros_acceso", "datos": {"id": registro[0], "estado": "ACTIVO"}}]}


def salida(cursor, placa):
    vehiculo_id, _, _ = _vehiculo(cursor, placa)
    registro = _registro_activo(cursor, vehiculo_id, bloquear=True)
    if not registro:
        raise ErrorParqueo(f"El vehículo {placa} no tiene un registro activo.", 409)
    registro_id, espacio_id, fecha_entrada = registro
    cursor.execute("""SELECT e.codigo,c.tarifa_por_hora FROM espacios e
        JOIN catalogo_espacios c ON c.id=e.catalogo_espacio_id WHERE e.id=%s""", [espacio_id])
    espacio = cursor.fetchone()
    if not espacio:
        raise ErrorParqueo("El espacio asociado al registro no existe.", 500)
    codigo, tarifa = espacio
    cursor.execute("""SELECT GREATEST(1, CEILING(GREATEST(0,TIMESTAMPDIFF(MINUTE,fecha_entrada,NOW()))/60.0))
        FROM registros_acceso WHERE id=%s""", [registro_id])
    horas = int(cursor.fetchone()[0])
    monto = (Decimal(str(tarifa)) * horas).quantize(Decimal('0.01'))
    # Cerrar registro y liberar espacio en la misma transacción.
    cursor.execute("UPDATE registros_acceso SET fecha_salida=NOW(), estado='FINALIZADO', monto_total=%s WHERE id=%s AND estado='ACTIVO'", [monto, registro_id])
    if cursor.rowcount != 1:
        raise ErrorParqueo("No se pudo cerrar el registro activo; inténtalo nuevamente.", 409)
    cursor.execute("UPDATE espacios SET estado='LIBRE' WHERE id=%s", [espacio_id])
    cursor.execute("SELECT fecha_salida FROM registros_acceso WHERE id=%s", [registro_id])
    fecha_salida = cursor.fetchone()[0]
    fecha_salida_json = fecha_salida.isoformat() if hasattr(fecha_salida, 'isoformat') else str(fecha_salida)
    return {"resultado": {"registro_id": registro_id, "placa": placa, "espacio": codigo,
            "fecha_salida": fecha_salida_json, "horas_cobradas": horas, "monto_total": float(monto), "estado": "FINALIZADO", "espacio_liberado": True},
            "traduccion_bd": [
                {"operacion": "UPDATE", "tabla": "registros_acceso", "datos": {"id": registro_id, "estado": "FINALIZADO", "monto_total": float(monto), "fecha_salida": "NOW()"}},
                {"operacion": "UPDATE", "tabla": "espacios", "datos": {"id": espacio_id, "codigo": codigo, "estado": "LIBRE"}}]}


def apagar_alarma(cursor, placa):
    vehiculo_id, _, _ = _vehiculo(cursor, placa)
    # Descubre columnas reales para no asumir un esquema no visible en la captura.
    cursor.execute("SELECT COLUMN_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='alarmas'")
    columnas = {row[0] for row in cursor.fetchall()}
    if not columnas:
        raise ErrorParqueo("No existe la tabla alarmas en la base de datos seleccionada.", 500)
    fk = next((c for c in ("vehiculo_id", "id_vehiculo") if c in columnas), None)
    estado_col = next((c for c in ("estado", "activa", "status") if c in columnas), None)
    if not fk or not estado_col:
        raise ErrorParqueo("La tabla alarmas no tiene columnas reconocibles para relacionar vehículo y estado; revisa su estructura.", 500)
    if estado_col == "activa":
        cursor.execute(f"UPDATE alarmas SET `{estado_col}`=0 WHERE `{fk}`=%s", [vehiculo_id])
    else:
        cursor.execute(f"UPDATE alarmas SET `{estado_col}`='APAGADA' WHERE `{fk}`=%s AND UPPER(CAST(`{estado_col}` AS CHAR)) IN ('ACTIVA','ENCENDIDA','ON')", [vehiculo_id])
    afectadas = cursor.rowcount
    return {"resultado": {"placa": placa, "alarmas_actualizadas": afectadas, "apagada": afectadas > 0},
            "traduccion_bd": [{"operacion": "UPDATE", "tabla": "alarmas", "datos": {"vehiculo_id": vehiculo_id, "estado": "APAGADA", "filas_afectadas": afectadas}}]}


def consultar(cursor):
    cursor.execute("""SELECT r.id AS registro_id,v.placa,e.codigo AS espacio,e.ubicacion,
        r.fecha_entrada,r.estado,r.monto_total FROM registros_acceso r
        JOIN vehiculos v ON v.id=r.vehiculo_id JOIN espacios e ON e.id=r.espacio_id
        WHERE r.estado='ACTIVO' ORDER BY r.fecha_entrada DESC""")
    cols = [c[0] for c in cursor.description]
    rows = [{k: (v.isoformat() if hasattr(v, 'isoformat') else float(v) if isinstance(v, Decimal) else v)
             for k, v in zip(cols, row)} for row in cursor.fetchall()]
    return {"resultado": {"registros_activos": rows, "total": len(rows)},
            "traduccion_bd": [{"operacion": "SELECT", "tabla": "registros_acceso", "filtro": "estado=ACTIVO"}]}


def ejecutar(instruccion, usuario_id=None):
    """Ejecuta exclusivamente instrucciones que el autómata ya reconoció."""
    accion = instruccion["accion"]
    with transaction.atomic():
        with connection.cursor() as cursor:
            if accion == "REGISTRAR":
                return registrar_vehiculo(cursor, instruccion["tipo"], instruccion["placa"])
            if accion in ("ASIGNAR", "LLEGADA"):
                return llegada(cursor, instruccion["placa"], usuario_id)
            if accion == "AUTORIZAR_SALIDA":
                return autorizar_salida(cursor, instruccion["placa"])
            if accion == "SALIDA":
                return salida(cursor, instruccion["placa"])
            if accion == "APAGAR_ALARMA":
                return apagar_alarma(cursor, instruccion["placa"])
            if accion == "CONSULTAR":
                return consultar(cursor)
    raise ErrorParqueo(f"La acción {accion} no está implementada.", 501)
