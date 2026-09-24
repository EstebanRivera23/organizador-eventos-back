from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def health_check(request):
    return Response({
        "status": "ok",
        "message": "API funcionando correctamente",
        "sprint": "Sprint 0",
        "framework": "Django REST Framework"
    })
