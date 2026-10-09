from decimal import Decimal

from rest_framework import serializers
from .estados import MENSAJE_ESTADO_INVALIDO, normalizar_estado
from .models import Evento, Subtarea

LIMITE_MINIMO = Decimal("1")
LIMITE_MAXIMO = Decimal("16")
MENSAJE_RANGO_LIMITE = "El límite debe estar entre 1 y 16 horas por día."
MENSAJE_LIMITE_INVALIDO = "Escribe el límite como un número de horas, por ejemplo 6 o 4.5."


class RegistroSerializer(serializers.Serializer):
    nombre = serializers.CharField(
        max_length=120,
        error_messages={
            "required": "Este campo es obligatorio.",
            "blank": "Este campo es obligatorio.",
            "null": "Este campo es obligatorio.",
            "max_length": "El nombre es demasiado largo.",
        },
    )
    email = serializers.EmailField(
        error_messages={
            "required": "Este campo es obligatorio.",
            "blank": "Este campo es obligatorio.",
            "null": "Este campo es obligatorio.",
            "invalid": "Escribe un correo válido, por ejemplo ana@correo.com.",
        },
    )
    password = serializers.CharField(
        min_length=6,
        write_only=True,
        error_messages={
            "required": "Este campo es obligatorio.",
            "blank": "Este campo es obligatorio.",
            "null": "Este campo es obligatorio.",
            "min_length": "La contraseña debe tener al menos 6 caracteres.",
        },
    )

    def validate_email(self, value):
        return value.strip().lower()


class LimiteDiarioSerializer(serializers.Serializer):
    limite_horas_dia = serializers.DecimalField(
        max_digits=4,
        decimal_places=2,
        min_value=LIMITE_MINIMO,
        max_value=LIMITE_MAXIMO,
        error_messages={
            "required": "Este campo es obligatorio.",
            "null": "Este campo es obligatorio.",
            "invalid": MENSAJE_LIMITE_INVALIDO,
            "min_value": MENSAJE_RANGO_LIMITE,
            "max_value": MENSAJE_RANGO_LIMITE,
            "max_digits": MENSAJE_RANGO_LIMITE,
            "max_whole_digits": MENSAJE_RANGO_LIMITE,
            "max_decimal_places": "El límite admite máximo dos decimales.",
        },
    )


class SubtareaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subtarea
        fields = [
            "id",
            "evento",
            "titulo",
            "descripcion",
            "fecha_objetivo",
            "horas_estimadas",
            "estado",
            "created_at",
        ]
        read_only_fields = ["id", "evento", "created_at"]

    def validate_titulo(self, value):
        if not value.strip():
            raise serializers.ValidationError("El título de la subtarea es obligatorio.")
        return value

    def validate_horas_estimadas(self, value):
        if value <= 0:
            raise serializers.ValidationError(
                "Las horas estimadas deben ser mayores a 0."
            )
        return value

    def validate_estado(self, value):
        estado = normalizar_estado(value)
        if estado is None:
            raise serializers.ValidationError(MENSAJE_ESTADO_INVALIDO)
        return estado


class EventoSerializer(serializers.ModelSerializer):
    subtareas = SubtareaSerializer(many=True, read_only=True)

    class Meta:
        model = Evento
        fields = [
            "id",
            "organizador",
            "nombre",
            "tipo",
            "cliente_contacto",
            "fecha_hora",
            "lugar",
            "plazo_limite",
            "estado",
            "created_at",
            "subtareas",
        ]
        read_only_fields = ["id", "organizador", "estado", "created_at", "subtareas"]

    def validate_nombre(self, value):
        if not value.strip():
            raise serializers.ValidationError("El nombre del evento es obligatorio.")
        return value

    def validate_tipo(self, value):
        if not value.strip():
            raise serializers.ValidationError("El tipo de evento es obligatorio.")
        return value

    def validate_cliente_contacto(self, value):
        if not value.strip():
            raise serializers.ValidationError("El cliente o contacto es obligatorio.")
        return value

    def validate_lugar(self, value):
        if not value.strip():
            raise serializers.ValidationError("El lugar del evento es obligatorio.")
        return value
