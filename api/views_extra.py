"""Vistas nuevas: alarmas (ESP32 <-> Django <-> Front) y login de usuarios.

Archivo aparte para no tocar api/views.py: solo reutiliza sus helpers
(leer, error) que ya estaban pensados para reusarse igual.
"""
from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from . import alarmas, usuarios
from .errors import ErrorParqueo
from .views import error, leer


@require_POST
def alarma_activar(request):
    """ESP32 -> Django, cuando se prende el buzzer por mal estacionado."""
    try:
        d = leer(request)
        if not {'placa', 'cajon'} <= set(d) or set(d) - {'placa', 'cajon', 'motivo'}:
            raise ErrorParqueo('Envía placa, cajon y opcionalmente motivo.', 400)
        return JsonResponse(alarmas.activar(d.get('placa'), d.get('cajon'), d.get('motivo')))
    except ErrorParqueo as e:
        return error(e)


@require_POST
def alarma_silenciar(request):
    """Front (operador) -> Django, botón "Callar alarma"."""
    try:
        d = leer(request)
        if set(d) != {'placa'}:
            raise ErrorParqueo('Envía únicamente placa.', 400)
        return JsonResponse(alarmas.silenciar(d['placa']))
    except ErrorParqueo as e:
        return error(e)


@require_GET
def alarma_estado(request):
    """ESP32 -> Django, polling cada 2-3s mientras el buzzer suena."""
    try:
        return JsonResponse(alarmas.estado_de(request.GET.get('placa')))
    except ErrorParqueo as e:
        return error(e)


@require_GET
def alarmas_listar(request):
    """Front -> Django, para pintar la tabla de la pestaña Alarmas."""
    try:
        return JsonResponse(alarmas.listar(request.GET.get('estado')), safe=False)
    except ErrorParqueo as e:
        return error(e)


@require_POST
def login(request):
    """Front -> Django, pantalla de login del administrador."""
    try:
        d = leer(request)
        if set(d) != {'username', 'password'}:
            raise ErrorParqueo('Envía username y password.', 400)
        return JsonResponse(usuarios.validar_login(d['username'], d['password']))
    except ErrorParqueo as e:
        return error(e)
