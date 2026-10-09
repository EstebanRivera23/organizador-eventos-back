from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.db import IntegrityError

from drf_spectacular.utils import extend_schema

from . import documentacion as doc
from .estados import MENSAJE_ESTADO_INVALIDO, formas_de, normalizar_estado
from .models import Organizador, Evento, Subtarea
from .serializers import (
    EventoSerializer,
    LimiteDiarioSerializer,
    RegistroSerializer,
    SubtareaSerializer,
)


@extend_schema(
    tags=["Estado"],
    summary="Comprobar que la API está viva",
    auth=[],
    responses=doc.EstadoApiSerializer,
)
@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API funcionando correctamente",
        "sprint": "Sprint 3",
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


def sesion_de(organizador, mensaje):
    """Lo que se le devuelve al front cuando alguien entra: token y perfil."""
    token = signing.dumps(
        str(organizador.id),
        salt="organizador-login"
    )

    return {
        "message": mensaje,
        "token": token,
        "organizador": {
            "id": str(organizador.id),
            "nombre": organizador.nombre,
            "email": organizador.email
        }
    }


CORREO_YA_REGISTRADO = {"email": ["Ya existe una cuenta con este correo."]}


@extend_schema(
    tags=["Sesión"],
    summary="Crear una cuenta",
    description=(
        "Registra un organizador nuevo y lo deja con la sesión iniciada: "
        "devuelve el mismo token que el login."
    ),
    auth=[],
    request=RegistroSerializer,
    responses={201: doc.SesionSerializer, 400: doc.DATOS_INVALIDOS},
    examples=[
        doc.EJEMPLO_REGISTRO,
        doc.EJEMPLO_CUENTA_CREADA,
        doc.EJEMPLO_CORREO_REPETIDO,
    ],
)
@api_view(["POST"])
def registro(request):
    serializer = RegistroSerializer(data=request.data)
    if not serializer.is_valid():
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    datos = serializer.validated_data
    if Organizador.objects.filter(email=datos["email"]).exists():
        return Response(CORREO_YA_REGISTRADO, status=status.HTTP_400_BAD_REQUEST)

    try:
        organizador = Organizador.objects.create(
            nombre=datos["nombre"],
            email=datos["email"],
            password_hash=make_password(datos["password"]),
        )
    except IntegrityError:
        # Dos registros con el mismo correo al mismo tiempo.
        return Response(CORREO_YA_REGISTRADO, status=status.HTTP_400_BAD_REQUEST)

    return Response(
        sesion_de(organizador, "Cuenta creada"),
        status=status.HTTP_201_CREATED
    )


@extend_schema(
    tags=["Sesión"],
    summary="Iniciar sesión",
    description=(
        "Devuelve el token que se manda en las demás peticiones como "
        "`Authorization: Bearer <token>`. Dura 8 horas. Solo entran las "
        "cuentas creadas en el registro."
    ),
    auth=[],
    request=doc.LoginSerializer,
    responses={
        200: doc.SesionSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.ErrorSerializer,
    },
    examples=[doc.EJEMPLO_LOGIN, doc.EJEMPLO_SESION, doc.EJEMPLO_CREDENCIALES],
)
@api_view(["POST"])
def login(request):
    """
    Inicia sesión con correo y contraseña. Solo entran las cuentas que ya
    están registradas.

    Si el correo no existe o la contraseña no es, responde lo mismo, para no
    revelar qué correos tienen cuenta.
    """
    email = str(request.data.get("email", "")).strip().lower()
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

    organizador = Organizador.objects.filter(email=email).first()

    if (
        organizador is None
        or not organizador.password_hash
        or not check_password(password, organizador.password_hash)
    ):
        return Response(
            {"detail": "Credenciales inválidas."},
            status=status.HTTP_401_UNAUTHORIZED
        )

    return Response(
        sesion_de(organizador, "Login correcto"),
        status=status.HTTP_200_OK
    )


@extend_schema(
    tags=["Sesión"],
    summary="Datos del organizador que tiene la sesión",
    responses={200: doc.OrganizadorSerializer, 401: doc.NO_AUTENTICADO},
)
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


DIAS_PARA_SUGERIR = 14
MAXIMO_FECHAS_SUGERIDAS = 3


def horas_por_dia(organizador, desde, hasta, sin_subtarea=None):
    """
    Horas de gestión sin finalizar del organizador en cada día del rango,
    sumando todos sus eventos. Los días sin gestiones no aparecen.
    """
    gestiones = Subtarea.objects.filter(
        evento__organizador=organizador,
        fecha_objetivo__range=(desde, hasta),
    ).exclude(estado__iexact="finalizado")

    if sin_subtarea is not None:
        gestiones = gestiones.exclude(pk=sin_subtarea.pk)

    filas = gestiones.values("fecha_objetivo").annotate(total=Sum("horas_estimadas"))
    return {fila["fecha_objetivo"]: fila["total"] for fila in filas}


def sugerir_fechas(organizador, subtarea, fecha, horas):
    """
    Días más cercanos a `fecha` en los que la gestión sí cabe sin pasar el
    límite diario. No sugiere días que ya pasaron ni posteriores al evento.
    """
    hoy = timezone.localdate()
    dia_del_evento = timezone.localtime(subtarea.evento.fecha_hora).date()
    limite = organizador.limite_horas_dia
    carga = horas_por_dia(
        organizador,
        fecha - timedelta(days=DIAS_PARA_SUGERIR),
        fecha + timedelta(days=DIAS_PARA_SUGERIR),
        sin_subtarea=subtarea,
    )

    sugeridas = []
    for distancia in range(1, DIAS_PARA_SUGERIR + 1):
        for candidata in (
            fecha + timedelta(days=distancia),
            fecha - timedelta(days=distancia),
        ):
            if candidata < hoy or candidata > dia_del_evento:
                continue

            horas_planificadas = carga.get(candidata, Decimal("0")) + horas
            if horas_planificadas <= limite:
                sugeridas.append({
                    "fecha": candidata,
                    "horas_planificadas": f"{horas_planificadas:.2f}",
                })

        if len(sugeridas) >= MAXIMO_FECHAS_SUGERIDAS:
            break

    sugeridas = sugeridas[:MAXIMO_FECHAS_SUGERIDAS]
    return sorted(sugeridas, key=lambda sugerida: sugerida["fecha"])


def carga_del_dia(organizador, fecha):
    """Cómo queda el día después de guardar: horas planificadas y límite."""
    horas = horas_por_dia(organizador, fecha, fecha).get(fecha, Decimal("0"))
    return {
        "fecha": fecha,
        "horas_planificadas": f"{horas:.2f}",
        "limite_horas_dia": f"{organizador.limite_horas_dia:.2f}",
    }


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

    otras_gestiones = horas_por_dia(
        organizador, fecha, fecha, sin_subtarea=subtarea
    ).get(fecha, Decimal("0"))

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
            "horas_disponibles": f"{max(limite - otras_gestiones, Decimal('0')):.2f}",
            "fechas_sugeridas": sugerir_fechas(organizador, subtarea, fecha, horas),
        },
    }


@extend_schema(
    methods=["GET"],
    tags=["Límite diario"],
    summary="Ver el límite diario de horas",
    description="Si el organizador nunca lo ha cambiado, responde 6.",
    responses={200: LimiteDiarioSerializer, 401: doc.NO_AUTENTICADO},
    examples=[doc.EJEMPLO_LIMITE],
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Límite diario"],
    summary="Cambiar el límite diario de horas",
    description=(
        "Solo acepta valores entre 1 y 16. El límite es de cada organizador y "
        "se usa desde ese momento para detectar la sobrecarga al reprogramar."
    ),
    request=LimiteDiarioSerializer,
    responses={
        200: LimiteDiarioSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
    },
    examples=[doc.EJEMPLO_LIMITE, doc.EJEMPLO_LIMITE_FUERA_DE_RANGO],
)
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


@extend_schema(
    methods=["GET"],
    tags=["Eventos"],
    operation_id="eventos_listar",
    summary="Listar los eventos del organizador",
    responses={200: EventoSerializer(many=True), 401: doc.NO_AUTENTICADO},
)
@extend_schema(
    methods=["POST"],
    tags=["Eventos"],
    operation_id="eventos_crear",
    summary="Crear un evento",
    request=EventoSerializer,
    responses={
        201: EventoSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
    },
)
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


@extend_schema(
    methods=["GET"],
    tags=["Eventos"],
    operation_id="eventos_ver",
    summary="Ver un evento con sus gestiones",
    responses={
        200: EventoSerializer,
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Eventos"],
    summary="Editar un evento",
    description="Se pueden mandar solo los campos que cambian.",
    request=EventoSerializer,
    responses={
        200: EventoSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
)
@extend_schema(
    methods=["DELETE"],
    tags=["Eventos"],
    summary="Eliminar un evento con sus gestiones",
    responses={
        204: None,
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
)
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


@extend_schema(
    methods=["GET"],
    tags=["Gestiones"],
    operation_id="gestiones_listar",
    summary="Listar las gestiones de un evento",
    responses={
        200: SubtareaSerializer(many=True),
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
)
@extend_schema(
    methods=["POST"],
    tags=["Gestiones"],
    operation_id="gestiones_crear",
    summary="Agregar una gestión a un evento",
    request=SubtareaSerializer,
    responses={
        201: SubtareaSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
)
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


@extend_schema(
    methods=["GET"],
    tags=["Gestiones"],
    operation_id="gestiones_ver",
    summary="Ver una gestión",
    responses={
        200: SubtareaSerializer,
        401: doc.NO_AUTENTICADO,
        404: doc.SUBTAREA_NO_ENCONTRADA,
    },
)
@extend_schema(
    methods=["PUT", "PATCH"],
    tags=["Gestiones"],
    summary="Editar o reprogramar una gestión",
    description=(
        "Se pueden mandar solo los campos que cambian. Para reprogramar se "
        "manda `fecha_objetivo`.\n\n"
        "Antes de guardar se suman las horas de las gestiones sin finalizar del "
        "organizador para ese día, en todos sus eventos. Si el cambio le agrega "
        "horas al día y el total pasa del límite diario, no guarda y responde "
        "409 con las cifras, las horas que quedan libres ese día y hasta tres "
        "fechas cercanas donde la gestión sí cabe.\n\n"
        "El conflicto se resuelve con otra petición igual: con una fecha que "
        "tenga espacio, o con la misma fecha y menos `horas_estimadas`."
    ),
    request=SubtareaSerializer,
    responses={
        200: doc.SubtareaGuardadaSerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
        404: doc.SUBTAREA_NO_ENCONTRADA,
        409: doc.SobrecargaSerializer,
    },
    examples=[
        doc.EJEMPLO_REPROGRAMAR,
        doc.EJEMPLO_REDUCIR,
        doc.EJEMPLO_GUARDADA,
        doc.EJEMPLO_SOBRECARGA,
    ],
)
@extend_schema(
    methods=["DELETE"],
    tags=["Gestiones"],
    summary="Eliminar una gestión",
    responses={
        204: None,
        401: doc.NO_AUTENTICADO,
        404: doc.SUBTAREA_NO_ENCONTRADA,
    },
)
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

            subtarea = serializer.save()
            return Response({
                **serializer.data,
                "carga_dia": carga_del_dia(organizador, subtarea.fecha_objetivo),
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    if request.method == "DELETE":
        subtarea.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Texto de la regla de orden, igual al que muestra el front en la vista Hoy.
REGLA_HOY = (
    "Se muestran primero las vencidas, luego las de hoy y después las "
    "próximas. Dentro de cada grupo van por fecha objetivo y, si empatan, "
    "primero la de menor esfuerzo estimado."
)


@extend_schema(
    tags=["Gestiones"],
    operation_id="gestiones_hoy",
    summary="Gestiones para la vista Hoy",
    description=(
        "Gestiones sin finalizar del organizador, agrupadas en vencidas, para "
        "hoy y próximas. Dentro de cada grupo van por fecha objetivo y, si "
        "empatan, primero la de menos horas."
    ),
    parameters=doc.FILTROS_HOY,
    responses={
        200: doc.GestionesHoySerializer,
        400: doc.DATOS_INVALIDOS,
        401: doc.NO_AUTENTICADO,
        404: doc.EVENTO_NO_ENCONTRADO,
    },
    examples=[doc.EJEMPLO_HOY],
)
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
        estado_pedido = normalizar_estado(estado)

        if estado_pedido is None:
            return Response(
                {"estado": [MENSAJE_ESTADO_INVALIDO]},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Incluye las gestiones guardadas con los nombres viejos del estado.
        coincide = Q()
        for forma in formas_de(estado_pedido):
            coincide |= Q(estado__iexact=forma)
        subtareas_base = subtareas_base.filter(coincide)

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
        "regla": REGLA_HOY,
        "vencidas": SubtareaSerializer(vencidas, many=True).data,
        "para_hoy": SubtareaSerializer(para_hoy, many=True).data,
        "proximas": SubtareaSerializer(proximas, many=True).data
    })