from rest_framework import serializers
from .models import Evento, Subtarea


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
