from django.urls import path

from . import views
from . import views_extra

urlpatterns = [
    path("espacios", views.espacios, name="espacios"),
    path("espacios/ocupados", views.espacios_ocupados, name="espacios-ocupados"),
    path("historial", views.historial, name="historial"),
    path("comando", views.comando, name="comando"),
]

urlpatterns += [
    path('rfid', views.rfid, name='rfid'),
    path('pago/confirmar', views.pago_confirmar, name='pago-confirmar'),
]

# Nueva interfaz ESP32: comandos literales, SIN lexer/parser del autómata.
urlpatterns += [
    path('rfid/comando', views.rfid_comando, name='rfid-comando'),
  # path('manual/pendiente', views.manual_pendiente, name='manual-pendiente'),
]

# Alarmas (ESP32 <-> Django <-> Front, por polling) y login de usuarios.
# Agregado nuevo: no modifica nada de lo que ya existía arriba.
urlpatterns += [
    path('alarma/activar', views_extra.alarma_activar, name='alarma-activar'),
    path('alarma/silenciar', views_extra.alarma_silenciar, name='alarma-silenciar'),
    path('alarma/estado', views_extra.alarma_estado, name='alarma-estado'),
    path('alarmas', views_extra.alarmas_listar, name='alarmas-listar'),
    path('login', views_extra.login, name='login'),
]
