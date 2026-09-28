from django.urls import path
from .views import (
    health_check,
    eventos_list_create,
    evento_detail,
    subtareas_by_evento,
    subtarea_detail,
)

urlpatterns = [
    path("health/", health_check, name="health_check"),

    path("eventos/", eventos_list_create, name="eventos_list_create"),
    path("eventos/<int:pk>/", evento_detail, name="evento_detail"),
    path(
        "eventos/<int:evento_id>/subtareas/",
        subtareas_by_evento,
        name="subtareas_by_evento"
    ),
    path("subtareas/<int:pk>/", subtarea_detail, name="subtarea_detail"),
]
