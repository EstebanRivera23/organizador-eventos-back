from django.urls import path

from .views import (
    health_check,
    login,
    organizador_me,
    limite_diario,
    eventos_list_create,
    evento_detail,
    subtareas_by_evento,
    subtarea_detail,
    subtareas_hoy,
)

urlpatterns = [
    path("health/", health_check, name="health_check"),

    path("login/", login, name="login"),
    path("organizador/me/", organizador_me, name="organizador_me"),
    path("organizador/limite-diario/", limite_diario, name="limite_diario"),

    path("eventos/", eventos_list_create, name="eventos_list_create"),
    path("eventos/<int:pk>/", evento_detail, name="evento_detail"),
    path("eventos/<int:evento_id>/subtareas/", subtareas_by_evento, name="subtareas_by_evento"),

    path("subtareas/hoy/", subtareas_hoy, name="subtareas_hoy"),
    path("subtareas/<int:pk>/", subtarea_detail, name="subtarea_detail"),
]