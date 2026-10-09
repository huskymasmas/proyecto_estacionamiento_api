"""Traduce las instrucciones del autómata (lexer/parser PLY) a operaciones SQL
sobre las tablas reales de estacionamiento_db."""
from django.db import connection, transaction


class ErrorParqueo(Exception):
    def __init__(self, mensaje, status=400):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status = status


# Vocabulario del autómata -> valores que acepta la BD (CHECK constraints)
TIPO_A_VEHICULO = {
    "compacto": "AUTOMOVIL",
    "grande": "CAMIONETA",
    "moto": "MOTOCICLETA",
    "reserva": "AUTOMOVIL",
    "carga": "CAMION_CARGA",
}

# tipo_vehiculo (tabla vehiculos) -> codigo_categoria (tabla catalogo_espacios)
VEHICULO_A_CATEGORIA = {
    "AUTOMOVIL": "COMPACTO",
    "CAMIONETA": "GRANDE",
    "MOTOCICLETA": "MOTO",
    "CAMION_CARGA": "CARGA",
}


def registrar_vehiculo(cursor, tipo, placa):
    """REGISTRAR(tipo,PLACA) -> INSERT en vehiculos."""
    cursor.execute("SELECT 1 FROM vehiculos WHERE placa = %s", [placa])
    if cursor.fetchone():
        raise ErrorParqueo(
            f"La placa {placa} ya está registrada. Usa ASIGNAR({placa}) para darle un espacio.", 409
        )

    tipo_bd = TIPO_A_VEHICULO[tipo]
    cursor.execute(
        "INSERT INTO vehiculos (placa, tipo_vehiculo) VALUES (%s, %s)",
        [placa, tipo_bd],
    )
    vehiculo_id = cursor.lastrowid

    return {
        "resultado": {"vehiculo_id": vehiculo_id, "placa": placa, "tipo_vehiculo": tipo_bd},
        "traduccion_bd": [
            {"operacion": "INSERT", "tabla": "vehiculos",
             "datos": {"placa": placa, "tipo_vehiculo": tipo_bd}},
        ],
    }


def asignar_espacio(cursor, placa, usuario_id=None):
    """ASIGNAR(PLACA) -> INSERT en registros_acceso + UPDATE de espacios.estado."""
    cursor.execute("SELECT id, tipo_vehiculo FROM vehiculos WHERE placa = %s", [placa])
    fila = cursor.fetchone()
    if not fila:
        raise ErrorParqueo(
            f"La placa {placa} no está registrada. Usa REGISTRAR(tipo,{placa}) primero.", 404
        )
    vehiculo_id, tipo_vehiculo = fila

    cursor.execute(
        "SELECT 1 FROM registros_acceso WHERE vehiculo_id = %s AND estado = 'ACTIVO'", [vehiculo_id]
    )
    if cursor.fetchone():
        raise ErrorParqueo(f"El vehículo {placa} ya tiene un espacio asignado.", 409)

    if usuario_id is not None:
        cursor.execute("SELECT 1 FROM usuarios WHERE id = %s AND activo = 1", [usuario_id])
        if not cursor.fetchone():
            raise ErrorParqueo(f"El usuario_id {usuario_id} no existe o está inactivo.", 400)

    categoria = VEHICULO_A_CATEGORIA[tipo_vehiculo]
    cursor.execute(
        """
        SELECT e.id, e.codigo, e.ubicacion
        FROM espacios e
        JOIN catalogo_espacios c ON c.id = e.catalogo_espacio_id
        WHERE c.codigo_categoria = %s AND c.activo = 1 AND e.estado = 'LIBRE'
        ORDER BY e.id
        LIMIT 1
        FOR UPDATE
        """,
        [categoria],
    )
    espacio = cursor.fetchone()
    if not espacio:
        raise ErrorParqueo(f"No hay espacios libres de la categoría {categoria}.", 409)
    espacio_id, espacio_codigo, ubicacion = espacio

    cursor.execute(
        """
        INSERT INTO registros_acceso (vehiculo_id, espacio_id, usuario_id, estado, monto_total)
        VALUES (%s, %s, %s, 'ACTIVO', 0.00)
        """,
        [vehiculo_id, espacio_id, usuario_id],
    )
    registro_id = cursor.lastrowid
    cursor.execute("SELECT fecha_entrada FROM registros_acceso WHERE id = %s", [registro_id])
    fecha_entrada = cursor.fetchone()[0]

    cursor.execute("UPDATE espacios SET estado = 'OCUPADO' WHERE id = %s", [espacio_id])

    return {
        "resultado": {
            "registro_id": registro_id,
            "placa": placa,
            "espacio": espacio_codigo,
            "ubicacion": ubicacion,
            "categoria": categoria,
            "fecha_entrada": fecha_entrada.isoformat(),
            "pago": "PENDIENTE",
        },
        "traduccion_bd": [
            {"operacion": "INSERT", "tabla": "registros_acceso",
             "datos": {"vehiculo_id": vehiculo_id, "espacio_id": espacio_id,
                       "usuario_id": usuario_id, "estado": "ACTIVO", "monto_total": 0.0}},
            {"operacion": "UPDATE", "tabla": "espacios",
             "datos": {"codigo": espacio_codigo, "estado": "OCUPADO"}},
        ],
    }


def ejecutar(instruccion, usuario_id=None):
    """Recibe la instrucción que produjo el parser y la ejecuta contra la BD
    dentro de una transacción (si algo falla, no queda nada a medias)."""
    accion = instruccion["accion"]

    if accion not in ("REGISTRAR", "ASIGNAR"):
        raise ErrorParqueo(
            f"El comando {accion} es válido en el lenguaje, pero aún no está implementado en la BD.", 501
        )

    with transaction.atomic():
        with connection.cursor() as cursor:
            if accion == "REGISTRAR":
                return registrar_vehiculo(cursor, instruccion["tipo"], instruccion["placa"])
            return asignar_espacio(cursor, instruccion["placa"], usuario_id)
