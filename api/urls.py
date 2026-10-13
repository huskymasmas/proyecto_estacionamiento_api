from django.urls import path

from . import views

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
