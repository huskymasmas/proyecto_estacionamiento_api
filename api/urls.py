from django.urls import path

from . import views

urlpatterns = [
    path("espacios", views.espacios, name="espacios"),
    path("espacios/ocupados", views.espacios_ocupados, name="espacios-ocupados"),
    path("historial", views.historial, name="historial"),
    path("comando", views.comando, name="comando"),
]
