"""Login simple contra la tabla usuariosnuevo (usuario/contraseña hasheados).

No crea tokens de sesión: valida las credenciales y devuelve los datos del
usuario. Si luego quieren mantener la sesión abierta en el front, eso es un
cambio aparte (token o sesión) que no estaba pedido todavía.
"""
from django.contrib.auth.hashers import check_password
from django.db import connection

from .errors import ErrorParqueo


def validar_login(username, password):
    if not isinstance(username, str) or not username.strip():
        raise ErrorParqueo('Falta username.', 400)
    if not isinstance(password, str) or not password:
        raise ErrorParqueo('Falta password.', 400)
    username = username.strip()

    with connection.cursor() as c:
        c.execute("""SELECT id, username, password_hash, nombre_completo, rol, activo
            FROM usuariosnuevo WHERE username=%s LIMIT 1""", [username])
        fila = c.fetchone()

    if not fila:
        raise ErrorParqueo('Usuario o contraseña incorrectos.', 401)
    uid, uname, password_hash, nombre_completo, rol, activo = fila
    if not activo:
        raise ErrorParqueo('Usuario deshabilitado.', 403)
    if not check_password(password, password_hash):
        raise ErrorParqueo('Usuario o contraseña incorrectos.', 401)

    return {'ok': True, 'usuario_id': uid, 'username': uname,
            'nombre_completo': nombre_completo, 'rol': rol}
