from django.utils import timezone
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
        "sprint": "Sprint 2",
        "framework": "Django REST Framework"
    })


def obtener_organizador_autenticado(request):
    """
    Login simple para Sprint 2.

    El frontend debe enviar el token recibido en /api/login/ así:
    Authorization: Bearer <organizador_id>

    Para pruebas también permite:
    X-Organizador-Id: <organizador_id>
    ?organizador_id=<organizador_id>
    """
    auth_header = request.headers.get("Authorization", "")
    token = ""

    if auth_header.startswith("Bearer "):
        token = auth_header.replace("Bearer ", "").strip()

    if not token:
        token = request.headers.get("X-Organizador-Id", "").strip()

    if not token:
        token = request.query_params.get("organizador_id", "").strip()

    if not token:
        return None, Response(
            {"detail": "No autenticado. Debe iniciar sesión."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    try:
        organizador = Organizador.objects.get(id=token)
    except (Organizador.DoesNotExist, ValueError):
        return None, Response(
            {"detail": "Token inválido o organizador no encontrado."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    return organizador, None


@api_view(["POST"])
def login(request):
    """
    Login básico por email para Sprint 2.

    Si el organizador existe, lo retorna.
    Si no existe, lo crea.
    """
    email = str(request.data.get("email", "")).strip().lower()
    nombre = str(request.data.get("nombre", "")).strip()

    if not email:
        return Response(
            {"email": ["Este campo es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not nombre:
        nombre = email.split("@")[0]

    organizador, created = Organizador.objects.get_or_create(
        email=email,
        defaults={"nombre": nombre}
    )

    if not created and nombre and organizador.nombre != nombre:
        organizador.nombre = nombre
        organizador.save(update_fields=["nombre"])

    return Response({
        "message": "Login correcto",
        "token": str(organizador.id),
        "organizador": {
            "id": str(organizador.id),
            "nombre": organizador.nombre,
            "email": organizador.email
        }
    }, status=status.HTTP_200_OK)


@api_view(["GET"])
def organizador_me(request):
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    return Response({
        "id": str(organizador.id),
        "nombre": organizador.nombre,
        "email": organizador.email
    })


@api_view(["GET", "POST"])
def eventos_list_create(request):
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    if request.method == "GET":
        eventos = Evento.objects.filter(organizador=organizador).order_by("-created_at")
        serializer = EventoSerializer(eventos, many=True)
        return Response(serializer.data)

    serializer = EventoSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(organizador=organizador)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def evento_detail(request, pk):
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    try:
        evento = Evento.objects.get(pk=pk, organizador=organizador)
    except Evento.DoesNotExist:
        return Response(
            {"detail": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = EventoSerializer(evento)
        return Response(serializer.data)

    if request.method in ["PUT", "PATCH"]:
        serializer = EventoSerializer(evento, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(organizador=organizador)
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        evento.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET", "POST"])
def subtareas_by_evento(request, evento_id):
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    try:
        evento = Evento.objects.get(pk=evento_id, organizador=organizador)
    except Evento.DoesNotExist:
        return Response(
            {"detail": "Evento no encontrado."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        subtareas = Subtarea.objects.filter(evento=evento).order_by("fecha_objetivo", "horas_estimadas")
        serializer = SubtareaSerializer(subtareas, many=True)
        return Response(serializer.data)

    serializer = SubtareaSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save(evento=evento)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET", "PUT", "PATCH", "DELETE"])
def subtarea_detail(request, pk):
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    try:
        subtarea = Subtarea.objects.get(pk=pk, evento__organizador=organizador)
    except Subtarea.DoesNotExist:
        return Response(
            {"detail": "Subtarea no encontrada."},
            status=status.HTTP_404_NOT_FOUND
        )

    if request.method == "GET":
        serializer = SubtareaSerializer(subtarea)
        return Response(serializer.data)

    if request.method in ["PUT", "PATCH"]:
        serializer = SubtareaSerializer(subtarea, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        subtarea.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
def subtareas_hoy(request):
    """
    Endpoint principal de Sprint 2 para alimentar la vista /hoy.

    Retorna subtareas pendientes agrupadas en:
    - vencidas
    - para_hoy
    - proximas

    Solo retorna subtareas del organizador autenticado.
    """
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    hoy = timezone.localdate()

    subtareas_base = Subtarea.objects.filter(
        evento__organizador=organizador
    ).exclude(
        estado__iexact="finalizado"
    )

    vencidas = subtareas_base.filter(
        fecha_objetivo__lt=hoy
    ).order_by("fecha_objetivo", "horas_estimadas")

    para_hoy = subtareas_base.filter(
        fecha_objetivo=hoy
    ).order_by("horas_estimadas", "fecha_objetivo")

    proximas = subtareas_base.filter(
        fecha_objetivo__gt=hoy
    ).order_by("fecha_objetivo", "horas_estimadas")

    return Response({
        "fecha_actual": hoy,
        "regla": "Se muestran primero las vencidas, luego las de hoy y después las próximas. En empate se prioriza menor esfuerzo estimado.",
        "vencidas": SubtareaSerializer(vencidas, many=True).data,
        "para_hoy": SubtareaSerializer(para_hoy, many=True).data,
        "proximas": SubtareaSerializer(proximas, many=True).data
    })