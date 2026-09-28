from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Organizador, Evento, Subtarea
from .serializers import EventoSerializer, SubtareaSerializer


@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API funcionando correctamente",
        "sprint": "Sprint 1",
        "framework": "Django REST Framework"
    })


def get_demo_organizador():
    organizador, created = Organizador.objects.get_or_create(
        email="demo@eventflow.com",
        defaults={
            "nombre": "Usuario Demo"
        }
    )
    return organizador


@api_view(["GET", "POST"])
def eventos_list_create(request):
    if request.method == "GET":
        eventos = Evento.objects.all().order_by("-created_at")
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method == "POST":
        serializer = EventoSerializer(data=request.data)

        if serializer.is_valid():
            organizador = get_demo_organizador()
            evento = serializer.save(organizador=organizador)
            response_serializer = EventoSerializer(evento)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "DELETE"])
def evento_detail(request, pk):
    try:
        evento = Evento.objects.get(pk=pk)
    except Evento.DoesNotExist:
        return Response(
            {"detail": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = EventoSerializer(evento)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method == "PUT":
        serializer = EventoSerializer(evento, data=request.data, partial=True)

        if serializer.is_valid():
            evento = serializer.save()
            response_serializer = EventoSerializer(evento)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        evento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
def subtareas_by_evento(request, evento_id):
    try:
        evento = Evento.objects.get(pk=evento_id)
    except Evento.DoesNotExist:
        return Response(
            {"detail": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        subtareas = evento.subtareas.all().order_by("fecha_objetivo")
        serializer = SubtareaSerializer(subtareas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method == "POST":
        serializer = SubtareaSerializer(data=request.data)

        if serializer.is_valid():
            subtarea = serializer.save(evento=evento)
            response_serializer = SubtareaSerializer(subtarea)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    

@api_view(["GET", "PUT", "PATCH", "DELETE"])
def subtarea_detail(request, pk):
    try:
        subtarea = Subtarea.objects.get(pk=pk)
    except Subtarea.DoesNotExist:
        return Response(
            {"detail": "Subtarea no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = SubtareaSerializer(subtarea)
        return Response(serializer.data, status=status.HTTP_200_OK)

    if request.method in ["PUT", "PATCH"]:
        serializer = SubtareaSerializer(subtarea, data=request.data, partial=True)

        if serializer.is_valid():
            subtarea = serializer.save()
            response_serializer = SubtareaSerializer(subtarea)
            return Response(response_serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        subtarea.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
