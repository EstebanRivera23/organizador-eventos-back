from decimal import Decimal

from django.db.models import Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing

from .models import Organizador, Evento, Subtarea
from .serializers import EventoSerializer, LimiteDiarioSerializer, SubtareaSerializer


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
    Valida token firmado para Sprint 2.

    El frontend debe enviar:
    Authorization: Bearer <token_firmado>
    """
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        return None, Response(
            {"detail": "No autenticado. Debe iniciar sesión."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    token = auth_header.replace("Bearer ", "").strip()

    try:
        organizador_id = signing.loads(
            token,
            salt="organizador-login",
            max_age=60 * 60 * 8
        )
        organizador = Organizador.objects.get(id=organizador_id)
    except signing.SignatureExpired:
        return None, Response(
            {"detail": "Sesión expirada. Debe iniciar sesión nuevamente."},
            status=status.HTTP_401_UNAUTHORIZED
        )
    except Exception:
        return None, Response(
            {"detail": "Token inválido o sesión no válida."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    return organizador, None


@api_view(["POST"])
def login(request):
    """
    Login con email y contraseña para Sprint 2.

    Si el email no existe, registra el organizador con la contraseña enviada.
    Si el email existe, valida la contraseña.
    """
    email = str(request.data.get("email", "")).strip().lower()
    nombre = str(request.data.get("nombre", "")).strip()
    password = str(request.data.get("password", "")).strip()

    if not email:
        return Response(
            {"email": ["Este campo es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not password:
        return Response(
            {"password": ["Este campo es obligatorio."]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if len(password) < 6:
        return Response(
            {"password": ["La contraseña debe tener al menos 6 caracteres."]},
            status=status.HTTP_400_BAD_REQUEST
        )

    if not nombre:
        nombre = email.split("@")[0]

    organizador = Organizador.objects.filter(email=email).first()

    if organizador is None:
        organizador = Organizador.objects.create(
            email=email,
            nombre=nombre,
            password_hash=make_password(password)
        )
    else:
        if not organizador.password_hash:
            organizador.password_hash = make_password(password)
            organizador.save(update_fields=["password_hash"])
        elif not check_password(password, organizador.password_hash):
            return Response(
                {"detail": "Credenciales inválidas."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if nombre and organizador.nombre != nombre:
            organizador.nombre = nombre
            organizador.save(update_fields=["nombre"])

    token = signing.dumps(
        str(organizador.id),
        salt="organizador-login"
    )

    return Response({
        "message": "Login correcto",
        "token": token,
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


def formato_horas(horas):
    """7.00 -> "7", 7.50 -> "7.5": así se muestran las horas en los mensajes."""
    texto = f"{horas:.2f}".rstrip("0").rstrip(".")
    return texto or "0"


def esta_finalizada(estado):
    return str(estado).strip().lower() == "finalizado"


def detectar_sobrecarga(organizador, subtarea, cambios):
    """
    Revisa si guardar los cambios deja el día por encima del límite diario.

    Suma las horas de todas las gestiones sin finalizar del organizador para
    la fecha en la que quedaría la gestión, en todos sus eventos. Solo hay
    conflicto si el cambio le agrega horas a ese día: reducir horas o cambiar
    el título de una gestión que ya estaba en un día cargado no se bloquea.

    Devuelve None si no hay conflicto, o el cuerpo de la respuesta 409.
    """
    fecha = cambios.get("fecha_objetivo", subtarea.fecha_objetivo)
    horas = cambios.get("horas_estimadas", subtarea.horas_estimadas)
    estado = cambios.get("estado", subtarea.estado)

    if esta_finalizada(estado):
        return None

    horas_antes = Decimal("0")
    if subtarea.fecha_objetivo == fecha and not esta_finalizada(subtarea.estado):
        horas_antes = subtarea.horas_estimadas

    if horas <= horas_antes:
        return None

    otras_gestiones = (
        Subtarea.objects.filter(
            evento__organizador=organizador,
            fecha_objetivo=fecha,
        )
        .exclude(estado__iexact="finalizado")
        .exclude(pk=subtarea.pk)
        .aggregate(total=Sum("horas_estimadas"))["total"]
        or Decimal("0")
    )

    limite = organizador.limite_horas_dia
    horas_planificadas = otras_gestiones + horas

    if horas_planificadas <= limite:
        return None

    return {
        "detail": (
            f"Quedarías con {formato_horas(horas_planificadas)}h planificadas "
            f"(límite {formato_horas(limite)}h)"
        ),
        "codigo": "sobrecarga_diaria",
        "conflicto": {
            "fecha": fecha,
            "horas_planificadas": f"{horas_planificadas:.2f}",
            "limite_horas_dia": f"{limite:.2f}",
            "excede_por": f"{horas_planificadas - limite:.2f}",
            "horas_otras_gestiones": f"{otras_gestiones:.2f}",
            "horas_gestion": f"{horas:.2f}",
        },
    }


@api_view(["GET", "PUT", "PATCH"])
def limite_diario(request):
    """
    Límite de horas de gestión por día del organizador autenticado.

    GET devuelve el límite actual (6 si nunca lo ha cambiado).
    PUT/PATCH lo actualiza; solo acepta valores entre 1 y 16.
    """
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    if request.method == "GET":
        serializer = LimiteDiarioSerializer(organizador)
        return Response(serializer.data)

    serializer = LimiteDiarioSerializer(data=request.data)
    if serializer.is_valid():
        organizador.limite_horas_dia = serializer.validated_data["limite_horas_dia"]
        organizador.save(update_fields=["limite_horas_dia"])
        return Response(LimiteDiarioSerializer(organizador).data)

    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            conflicto = detectar_sobrecarga(
                organizador, subtarea, serializer.validated_data
            )
            if conflicto:
                return Response(conflicto, status=status.HTTP_409_CONFLICT)

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

    Filtros opcionales:
    - evento_id
    - estado

    Solo retorna subtareas del organizador autenticado.
    """
    organizador, error = obtener_organizador_autenticado(request)
    if error:
        return error

    hoy = timezone.localdate()

    evento_id = request.query_params.get("evento_id")
    estado = request.query_params.get("estado")

    subtareas_base = Subtarea.objects.filter(
        evento__organizador=organizador
    )

    # Por defecto, no mostrar finalizadas en Vista Hoy
    subtareas_base = subtareas_base.exclude(
        estado__iexact="finalizado"
    )

    # Filtro por evento
    if evento_id:
        try:
            evento = Evento.objects.get(
                id=evento_id,
                organizador=organizador
            )
        except Evento.DoesNotExist:
            return Response(
                {"detail": "Evento no encontrado para este organizador."},
                status=status.HTTP_404_NOT_FOUND
            )

        subtareas_base = subtareas_base.filter(evento=evento)

    # Filtro por estado
    if estado:
        estados_validos = ["por hacer", "en curso", "finalizado"]

        if estado.lower() not in estados_validos:
            return Response(
                {
                    "estado": [
                        "Estado invalido. Use: por hacer, en curso o finalizado."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        subtareas_base = subtareas_base.filter(estado__iexact=estado)

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
        "filtros": {
            "evento_id": evento_id,
            "estado": estado
        },
        "regla": "Se muestran primero las vencidas, luego las de hoy y despues las proximas. En empate se prioriza menor esfuerzo estimado.",
        "vencidas": SubtareaSerializer(vencidas, many=True).data,
        "para_hoy": SubtareaSerializer(para_hoy, many=True).data,
        "proximas": SubtareaSerializer(proximas, many=True).data
    })