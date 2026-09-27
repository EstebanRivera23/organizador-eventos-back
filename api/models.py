import uuid
from django.db import models


class Organizador(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nombre = models.TextField()
    email = models.TextField(unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "organizador"
        managed = False

    def __str__(self):
        return self.nombre


class Evento(models.Model):
    id = models.BigAutoField(primary_key=True)
    organizador = models.ForeignKey(
        Organizador,
        on_delete=models.CASCADE,
        db_column="organizador_id",
        related_name="eventos"
    )
    nombre = models.TextField()
    tipo = models.TextField()
    cliente_contacto = models.TextField()
    fecha_hora = models.DateTimeField()
    lugar = models.TextField()
    plazo_limite = models.DateField(null=True, blank=True)
    estado = models.TextField(default="por hacer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "evento"
        managed = False

    def __str__(self):
        return self.nombre


class Subtarea(models.Model):
    id = models.BigAutoField(primary_key=True)
    evento = models.ForeignKey(
        Evento,
        on_delete=models.CASCADE,
        db_column="evento_id",
        related_name="subtareas"
    )
    titulo = models.TextField()
    descripcion = models.TextField(null=True, blank=True)
    fecha_objetivo = models.DateField()
    horas_estimadas = models.DecimalField(max_digits=4, decimal_places=2, default=1)
    estado = models.TextField(default="por hacer")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "subtarea"
        managed = False

    def __str__(self):
        return self.titulo


class LimiteDiario(models.Model):
    id = models.BigAutoField(primary_key=True)
    organizador = models.ForeignKey(
        Organizador,
        on_delete=models.CASCADE,
        db_column="organizador_id",
        related_name="limites_diarios"
    )
    fecha = models.DateField()
    horas_maximas = models.DecimalField(max_digits=4, decimal_places=2, default=6)

    class Meta:
        db_table = "limite_diario"
        managed = False
        unique_together = ("organizador", "fecha")

    def __str__(self):
        return f"{self.organizador} - {self.fecha}"

# Create your models here.
