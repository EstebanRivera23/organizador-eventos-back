"""
Lo que necesita Swagger (/api/docs/) para mostrar qué recibe y qué responde
cada endpoint. Aquí no hay lógica: solo la forma de los datos y ejemplos.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import serializers

from .serializers import SubtareaSerializer


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class EstadoApiSerializer(serializers.Serializer):
    status = serializers.CharField()
    message = serializers.CharField()
    sprint = serializers.CharField()
    framework = serializers.CharField()


class LoginSerializer(serializers.Serializer):
    email = serializers.CharField()
    password = serializers.CharField()


class OrganizadorSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    nombre = serializers.CharField()
    email = serializers.CharField()


class SesionSerializer(serializers.Serializer):
    message = serializers.CharField()
    token = serializers.CharField()
    organizador = OrganizadorSerializer()


class CargaDiaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    horas_planificadas = serializers.CharField()
    limite_horas_dia = serializers.CharField()


class SubtareaGuardadaSerializer(SubtareaSerializer):
    carga_dia = CargaDiaSerializer()

    class Meta(SubtareaSerializer.Meta):
        fields = SubtareaSerializer.Meta.fields + ["carga_dia"]


class FechaSugeridaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    horas_planificadas = serializers.CharField()


class ConflictoSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    horas_planificadas = serializers.CharField()
    limite_horas_dia = serializers.CharField()
    excede_por = serializers.CharField()
    horas_otras_gestiones = serializers.CharField()
    horas_gestion = serializers.CharField()
    horas_disponibles = serializers.CharField()
    fechas_sugeridas = FechaSugeridaSerializer(many=True)
    fecha_posponer = FechaSugeridaSerializer(allow_null=True)


class SobrecargaSerializer(serializers.Serializer):
    detail = serializers.CharField()
    codigo = serializers.CharField()
    conflicto = ConflictoSerializer()


class FiltrosHoySerializer(serializers.Serializer):
    evento_id = serializers.CharField(allow_null=True)
    estado = serializers.CharField(allow_null=True)


class GestionesHoySerializer(serializers.Serializer):
    fecha_actual = serializers.DateField()
    filtros = FiltrosHoySerializer()
    regla = serializers.CharField()
    vencidas = SubtareaSerializer(many=True)
    para_hoy = SubtareaSerializer(many=True)
    proximas = SubtareaSerializer(many=True)


NO_AUTENTICADO = OpenApiResponse(
    ErrorSerializer,
    description="Falta el token, no es válido o la sesión ya venció.",
)
EVENTO_NO_ENCONTRADO = OpenApiResponse(
    ErrorSerializer,
    description="El evento no existe o es de otro organizador.",
)
SUBTAREA_NO_ENCONTRADA = OpenApiResponse(
    ErrorSerializer,
    description="La gestión no existe o es de otro organizador.",
)
DATOS_INVALIDOS = OpenApiResponse(
    OpenApiTypes.OBJECT,
    description="Algún campo no es válido. Responde un mensaje por cada campo.",
)

FILTROS_HOY = [
    OpenApiParameter(
        "evento_id", int, description="Solo las gestiones de ese evento."
    ),
    OpenApiParameter(
        "estado",
        str,
        enum=["por hacer", "en curso", "finalizado"],
        description="Solo las gestiones en ese estado.",
    ),
]

GESTION = {
    "id": 36,
    "evento": 31,
    "titulo": "Buscar proveedores",
    "descripcion": None,
    "fecha_objetivo": "2026-10-12",
    "horas_estimadas": "2.00",
    "estado": "por hacer",
    "created_at": "2026-10-09T02:42:13.332695-05:00",
}

EJEMPLO_LOGIN = OpenApiExample(
    "Login",
    value={"email": "ana@correo.com", "password": "secreto123"},
    request_only=True,
)

EJEMPLO_SESION = OpenApiExample(
    "Sesión iniciada",
    value={
        "message": "Login correcto",
        "token": "IjNmYTg1ZjY0Ii...",
        "organizador": {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "nombre": "ana",
            "email": "ana@correo.com",
        },
    },
    response_only=True,
    status_codes=["200"],
)

EJEMPLO_REGISTRO = OpenApiExample(
    "Registro",
    value={"nombre": "Ana Gómez", "email": "ana@correo.com", "password": "secreto123"},
    request_only=True,
)

EJEMPLO_CUENTA_CREADA = OpenApiExample(
    "Cuenta creada",
    value={
        "message": "Cuenta creada",
        "token": "IjNmYTg1ZjY0Ii...",
        "organizador": {
            "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "nombre": "Ana Gómez",
            "email": "ana@correo.com",
        },
    },
    response_only=True,
    status_codes=["201"],
)

EJEMPLO_CORREO_REPETIDO = OpenApiExample(
    "El correo ya tiene cuenta",
    value={"email": ["Ya existe una cuenta con este correo."]},
    response_only=True,
    status_codes=["400"],
)

EJEMPLO_CREDENCIALES = OpenApiExample(
    "Correo o contraseña incorrectos",
    value={"detail": "Credenciales inválidas."},
    response_only=True,
    status_codes=["401"],
)

EJEMPLO_LIMITE = OpenApiExample(
    "Límite de 4 horas",
    value={"limite_horas_dia": "4.00"},
)

EJEMPLO_LIMITE_FUERA_DE_RANGO = OpenApiExample(
    "Fuera de rango",
    value={"limite_horas_dia": ["El límite debe estar entre 1 y 16 horas por día."]},
    response_only=True,
    status_codes=["400"],
)

EJEMPLO_REPROGRAMAR = OpenApiExample(
    "Reprogramar",
    value={"fecha_objetivo": "2026-10-12"},
    request_only=True,
)

EJEMPLO_REDUCIR = OpenApiExample(
    "Resolver el conflicto reduciendo horas",
    value={"fecha_objetivo": "2026-10-12", "horas_estimadas": 1},
    request_only=True,
)

EJEMPLO_GUARDADA = OpenApiExample(
    "Se guardó",
    value={
        **GESTION,
        "carga_dia": {
            "fecha": "2026-10-12",
            "horas_planificadas": "6.00",
            "limite_horas_dia": "6.00",
        },
    },
    response_only=True,
    status_codes=["200"],
)

EJEMPLO_SOBRECARGA = OpenApiExample(
    "El día queda sobrecargado",
    value={
        "detail": "Quedarías con 7h planificadas (límite 6h)",
        "codigo": "sobrecarga_diaria",
        "conflicto": {
            "fecha": "2026-10-12",
            "horas_planificadas": "7.00",
            "limite_horas_dia": "6.00",
            "excede_por": "1.00",
            "horas_otras_gestiones": "5.00",
            "horas_gestion": "2.00",
            "horas_disponibles": "1.00",
            "fechas_sugeridas": [
                {"fecha": "2026-10-11", "horas_planificadas": "2.00"},
                {"fecha": "2026-10-13", "horas_planificadas": "2.00"},
                {"fecha": "2026-10-14", "horas_planificadas": "2.00"},
            ],
            "fecha_posponer": {"fecha": "2026-10-13", "horas_planificadas": "2.00"},
        },
    },
    response_only=True,
    status_codes=["409"],
)

EJEMPLO_HOY = OpenApiExample(
    "Gestiones agrupadas",
    value={
        "fecha_actual": "2026-10-09",
        "filtros": {"evento_id": None, "estado": None},
        "regla": (
            "Se muestran primero las de hoy, luego las vencidas y después las "
            "próximas. Dentro de cada grupo van por fecha objetivo y, si empatan, "
            "primero la de menor esfuerzo estimado."
        ),
        "vencidas": [
            {**GESTION, "id": 34, "titulo": "Reservar salón", "fecha_objetivo": "2026-10-07"}
        ],
        "para_hoy": [
            {**GESTION, "id": 35, "titulo": "Confirmar catering", "fecha_objetivo": "2026-10-09"}
        ],
        "proximas": [GESTION],
    },
    response_only=True,
    status_codes=["200"],
)
