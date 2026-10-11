import ply.lex as lex


class ErrorLexico(Exception):
    """Carácter que el autómata no reconoce."""


# Lista de tokens
tokens = [
    'REGISTRAR',
    'ASIGNAR',
    'LLEGADA',
    'AUTORIZAR_SALIDA',
    'SALIDA',
    'APAGAR_ALARMA',
    'CONSULTAR',
    'TIPO',
    'PLACA',
    'LPAREN',
    'RPAREN',
    'COMMA'
]

# Símbolos
t_LPAREN = r'\('
t_RPAREN = r'\)'
t_COMMA = r','

# Palabras reservadas
t_REGISTRAR = r'REGISTRAR'
t_ASIGNAR = r'ASIGNAR'
t_LLEGADA = r'LLEGADA'
t_AUTORIZAR_SALIDA = r'AUTORIZAR[ \t]+SALIDA|AUTORIZAR_SALIDA'
t_SALIDA = r'SALIDA'
t_APAGAR_ALARMA = r'APAGAR_ALARMA'
t_CONSULTAR = r'CONSULTAR'


# Tipos de vehículo
def t_TIPO(t):
    r'(compacto|grande|moto|reserva|carga)'
    return t


# Placas: AAA999
def t_PLACA(t):
    r'[A-Z]{3}[0-9]{3}'
    return t


# Ignorar espacios, tabs y saltos de línea
t_ignore = ' \t\n'


def t_error(t):
    # En lugar de imprimir, se lanza el error para devolverlo en la respuesta de la API
    raise ErrorLexico(f"Caracter ilegal '{t.value[0]}' en la posición {t.lexpos}")


lexer = lex.lex()
