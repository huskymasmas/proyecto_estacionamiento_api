"""Compatibilidad con /api/rfid: lectura simple deshabilitada por ambigüedad.
Usa /api/rfid/comando con entrada o salida explícita.
"""
from .errors import ErrorParqueo
from .rfid_commands import confirmar_pago

def procesar_lectura(placa):
    raise ErrorParqueo('Utiliza /api/rfid/comando con ASIGNAR(PLACA) o SALIDA(PLACA).',400)
