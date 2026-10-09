"""
Estados de una gestión. El front antiguo guardaba "pendiente" y "en_progreso";
se aceptan como equivalentes para que esas gestiones sigan apareciendo.
"""
POR_HACER = "por hacer"
EN_CURSO = "en curso"
FINALIZADO = "finalizado"

ESTADOS = [POR_HACER, EN_CURSO, FINALIZADO]

EQUIVALENTES = {
    "pendiente": POR_HACER,
    "en_progreso": EN_CURSO,
    "en progreso": EN_CURSO,
}

MENSAJE_ESTADO_INVALIDO = "Estado inválido. Usa: por hacer, en curso o finalizado."


def normalizar_estado(valor):
    """Devuelve el estado como se guarda, o None si no es un estado válido."""
    estado = str(valor or "").strip().lower()
    estado = EQUIVALENTES.get(estado, estado)
    return estado if estado in ESTADOS else None


def formas_de(estado):
    """Todas las formas en que un estado puede estar guardado en la base."""
    return [estado] + [vieja for vieja, nueva in EQUIVALENTES.items() if nueva == estado]
