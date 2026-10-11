import threading

import ply.yacc as yacc

from .lexer_parqueo import tokens, lexer, ErrorLexico  # noqa: F401  (tokens lo necesita PLY)


class ErrorSintactico(Exception):
    """El comando no cumple la gramática del lenguaje."""


# Análisis semántico: cada regla solo construye la instrucción (accion + datos).
# La traducción a la base de datos se hace DESPUÉS, en backend_logic.py, y solo
# si todo el comando fue válido.

def p_programa(p):
    'programa : instruccion'
    p[0] = p[1]


def p_instruccion(p):
    '''instruccion : registrar
                   | asignar
                   | llegada
                   | autorizar_salida
                   | salida
                   | apagar_alarma
                   | consultar'''
    p[0] = p[1]


def p_registrar(p):
    'registrar : REGISTRAR LPAREN TIPO COMMA PLACA RPAREN'
    p[0] = {"accion": "REGISTRAR", "tipo": p[3], "placa": p[5]}

# Compatible con REGISTRAR(789XY, manual) sin quitar el orden anterior.
def p_registrar_placa_primero(p):
    'registrar : REGISTRAR LPAREN PLACA COMMA TIPO RPAREN'
    p[0] = {"accion": "REGISTRAR", "tipo": p[5], "placa": p[3]}


def p_asignar(p):
    'asignar : ASIGNAR LPAREN PLACA RPAREN'
    p[0] = {"accion": "ASIGNAR", "placa": p[3]}


def p_llegada(p):
    'llegada : LLEGADA LPAREN PLACA RPAREN'
    p[0] = {"accion": "LLEGADA", "placa": p[3]}


def p_autorizar_salida(p):
    'autorizar_salida : AUTORIZAR_SALIDA LPAREN PLACA RPAREN'
    p[0] = {"accion": "AUTORIZAR_SALIDA", "placa": p[3]}


def p_salida(p):
    'salida : SALIDA LPAREN PLACA RPAREN'
    p[0] = {"accion": "SALIDA", "placa": p[3]}


def p_apagar_alarma(p):
    'apagar_alarma : APAGAR_ALARMA LPAREN PLACA RPAREN'
    p[0] = {"accion": "APAGAR_ALARMA", "placa": p[3]}


def p_consultar(p):
    'consultar : CONSULTAR LPAREN RPAREN'
    p[0] = {"accion": "CONSULTAR"}


def p_error(p):
    if p is None:
        raise ErrorSintactico("Comando incompleto: se esperaba más texto al final.")
    raise ErrorSintactico(f"Token inesperado '{p.value}' (tipo {p.type}) en la posición {p.lexpos}.")


parser = yacc.yacc(debug=False, write_tables=False)
_lock = threading.Lock()  # el parser de PLY guarda estado interno: no es thread-safe


def interpretar_comando(comando: str):
    """Pasa el texto por el lexer y el parser. Devuelve la instrucción (dict)
    o lanza ErrorLexico / ErrorSintactico."""
    with _lock:
        return parser.parse(comando, lexer=lexer.clone())
