from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Organizador, Subtarea

URL_LIMITE = "/api/organizador/limite-diario/"


class ApiTestCase(APITestCase):
    def entrar(self, email):
        """Crea la cuenta (o entra) y deja el token puesto en el cliente."""
        respuesta = self.client.post(
            "/api/login/", {"email": email, "password": "prueba123"}, format="json"
        )
        self.assertEqual(respuesta.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return Organizador.objects.get(email=email)

    def crear_evento(self, nombre="Boda de prueba"):
        respuesta = self.client.post(
            "/api/eventos/",
            {
                "nombre": nombre,
                "tipo": "boda",
                "cliente_contacto": "Cliente de prueba",
                "fecha_hora": "2030-01-15T18:00:00-05:00",
                "lugar": "Salón de prueba",
            },
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data["id"]

    def crear_gestion(self, evento_id, titulo, fecha, horas, estado=None):
        datos = {"titulo": titulo, "fecha_objetivo": str(fecha), "horas_estimadas": horas}
        if estado:
            datos["estado"] = estado
        respuesta = self.client.post(
            f"/api/eventos/{evento_id}/subtareas/", datos, format="json"
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data["id"]

    def cambiar_gestion(self, gestion_id, **cambios):
        cambios = {campo: str(valor) for campo, valor in cambios.items()}
        return self.client.patch(f"/api/subtareas/{gestion_id}/", cambios, format="json")


class LimiteDiarioTests(ApiTestCase):
    def test_sin_sesion_responde_401(self):
        self.assertEqual(self.client.get(URL_LIMITE).status_code, 401)
        respuesta = self.client.put(URL_LIMITE, {"limite_horas_dia": 4}, format="json")
        self.assertEqual(respuesta.status_code, 401)

    def test_por_defecto_es_6(self):
        self.entrar("prueba1@correo.com")
        respuesta = self.client.get(URL_LIMITE)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Decimal(respuesta.data["limite_horas_dia"]), Decimal("6"))

    def test_actualizar_guarda_el_nuevo_limite(self):
        organizador = self.entrar("prueba1@correo.com")
        respuesta = self.client.put(URL_LIMITE, {"limite_horas_dia": 4}, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Decimal(respuesta.data["limite_horas_dia"]), Decimal("4"))

        organizador.refresh_from_db()
        self.assertEqual(organizador.limite_horas_dia, Decimal("4"))
        self.assertEqual(
            Decimal(self.client.get(URL_LIMITE).data["limite_horas_dia"]), Decimal("4")
        )

    def test_acepta_los_extremos_y_decimales(self):
        self.entrar("prueba1@correo.com")
        for valor in (1, 16, "4.5"):
            respuesta = self.client.put(
                URL_LIMITE, {"limite_horas_dia": valor}, format="json"
            )
            self.assertEqual(respuesta.status_code, 200, valor)

    def test_fuera_de_rango_no_guarda_y_dice_el_rango(self):
        organizador = self.entrar("prueba1@correo.com")
        for valor in (0, 0.5, -3, 16.01, 17, 100):
            respuesta = self.client.put(
                URL_LIMITE, {"limite_horas_dia": valor}, format="json"
            )
            self.assertEqual(respuesta.status_code, 400, valor)
            self.assertIn("entre 1 y 16", respuesta.data["limite_horas_dia"][0])

        organizador.refresh_from_db()
        self.assertEqual(organizador.limite_horas_dia, Decimal("6"))

    def test_valor_que_no_es_numero_o_falta(self):
        self.entrar("prueba1@correo.com")
        for cuerpo in ({"limite_horas_dia": "muchas"}, {"limite_horas_dia": ""}, {}):
            respuesta = self.client.put(URL_LIMITE, cuerpo, format="json")
            self.assertEqual(respuesta.status_code, 400, cuerpo)
            self.assertIn("limite_horas_dia", respuesta.data)

    def test_el_limite_de_un_organizador_no_afecta_al_otro(self):
        self.entrar("prueba1@correo.com")
        self.client.put(URL_LIMITE, {"limite_horas_dia": 4}, format="json")

        self.entrar("prueba2@correo.com")
        self.assertEqual(
            Decimal(self.client.get(URL_LIMITE).data["limite_horas_dia"]), Decimal("6")
        )
        self.client.put(URL_LIMITE, {"limite_horas_dia": 9}, format="json")

        self.entrar("prueba1@correo.com")
        self.assertEqual(
            Decimal(self.client.get(URL_LIMITE).data["limite_horas_dia"]), Decimal("4")
        )


DIA_X = date(2030, 1, 10)
OTRO_DIA = DIA_X + timedelta(days=1)


class SobrecargaDiariaTests(ApiTestCase):
    def setUp(self):
        self.entrar("prueba1@correo.com")
        self.evento = self.crear_evento()

    def test_conflicto_con_cifras_y_no_guarda(self):
        """US-07 escenario 1: límite 6, día con 5 h, muevo una gestión de 2 h."""
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(
            respuesta.data["detail"],
            "Quedarías con 7h planificadas (límite 6h)",
        )
        self.assertEqual(respuesta.data["codigo"], "sobrecarga_diaria")
        conflicto = respuesta.data["conflicto"]
        self.assertEqual(str(conflicto["fecha"]), str(DIA_X))
        self.assertEqual(conflicto["horas_planificadas"], "7.00")
        self.assertEqual(conflicto["limite_horas_dia"], "6.00")
        self.assertEqual(conflicto["excede_por"], "1.00")
        self.assertEqual(conflicto["horas_otras_gestiones"], "5.00")
        self.assertEqual(conflicto["horas_gestion"], "2.00")
        self.assertEqual(Subtarea.objects.get(pk=proveedores).fecha_objetivo, OTRO_DIA)

    def test_sin_conflicto_guarda(self):
        """US-07 escenario 2: límite 6, día con 4 h, muevo una gestión de 2 h."""
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 4)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Subtarea.objects.get(pk=proveedores).fecha_objetivo, DIA_X)

    def test_mensaje_con_decimales(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5.5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(
            respuesta.data["detail"],
            "Quedarías con 7.5h planificadas (límite 6h)",
        )

    def test_las_finalizadas_no_cuentan(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 3)
        self.crear_gestion(self.evento, "Enviar invitaciones", DIA_X, 2, estado="finalizado")
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 200)

    def test_cuenta_las_gestiones_de_todos_los_eventos(self):
        otro_evento = self.crear_evento("Cumpleaños de prueba")
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 3)
        self.crear_gestion(otro_evento, "Confirmar catering", DIA_X, 2)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["conflicto"]["horas_planificadas"], "7.00")

    def test_no_cuenta_las_gestiones_de_otro_organizador(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)

        self.entrar("prueba2@correo.com")
        evento = self.crear_evento()
        proveedores = self.crear_gestion(evento, "Buscar proveedores", OTRO_DIA, 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 200)

    def test_usa_el_limite_configurado(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 3)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        self.client.put(URL_LIMITE, {"limite_horas_dia": 4}, format="json")
        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(
            respuesta.data["detail"],
            "Quedarías con 5h planificadas (límite 4h)",
        )

        self.client.put(URL_LIMITE, {"limite_horas_dia": 5}, format="json")
        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)
        self.assertEqual(respuesta.status_code, 200)

    def test_justo_en_el_limite_no_es_conflicto(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 4)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", OTRO_DIA, 2)

        self.assertEqual(
            self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X).status_code, 200
        )

    def test_subir_horas_en_el_mismo_dia_tambien_se_revisa(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 4)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", DIA_X, 2)

        respuesta = self.cambiar_gestion(proveedores, horas_estimadas=3)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["conflicto"]["horas_planificadas"], "7.00")
        self.assertEqual(Subtarea.objects.get(pk=proveedores).horas_estimadas, Decimal("2"))

    def test_en_un_dia_ya_cargado_se_puede_editar_o_reducir(self):
        # Al crear gestiones no se revisa el límite, así que el día puede venir cargado.
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", DIA_X, 4)

        self.assertEqual(
            self.cambiar_gestion(proveedores, titulo="Buscar proveedores de sonido").status_code,
            200,
        )
        self.assertEqual(
            self.cambiar_gestion(proveedores, horas_estimadas=3).status_code, 200
        )
        self.assertEqual(
            self.cambiar_gestion(proveedores, estado="finalizado").status_code, 200
        )

    def test_reabrir_una_finalizada_en_un_dia_lleno_es_conflicto(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(
            self.evento, "Buscar proveedores", DIA_X, 2, estado="finalizado"
        )

        respuesta = self.cambiar_gestion(proveedores, estado="por hacer")

        self.assertEqual(respuesta.status_code, 409)

    def test_no_se_puede_reprogramar_la_gestion_de_otro(self):
        ajena = self.crear_gestion(self.evento, "Reservar salón", DIA_X, 1)

        self.entrar("prueba2@correo.com")
        respuesta = self.cambiar_gestion(ajena, fecha_objetivo=OTRO_DIA)

        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(Subtarea.objects.get(pk=ajena).fecha_objetivo, DIA_X)

    def test_reprogramar_cambia_el_grupo_en_hoy(self):
        """US-06: la gestión reprogramada sale en el grupo que le toca en /hoy."""
        ayer = timezone.localdate() - timedelta(days=1)
        manana = timezone.localdate() + timedelta(days=1)
        gestion = self.crear_gestion(self.evento, "Buscar proveedores", ayer, 2)

        hoy = self.client.get("/api/subtareas/hoy/").data
        self.assertEqual([g["id"] for g in hoy["vencidas"]], [gestion])

        self.assertEqual(self.cambiar_gestion(gestion, fecha_objetivo=manana).status_code, 200)

        hoy = self.client.get("/api/subtareas/hoy/").data
        self.assertEqual(hoy["vencidas"], [])
        self.assertEqual([g["id"] for g in hoy["proximas"]], [gestion])

    def test_fecha_invalida_responde_400(self):
        gestion = self.crear_gestion(self.evento, "Buscar proveedores", DIA_X, 2)

        respuesta = self.cambiar_gestion(gestion, fecha_objetivo="mañana")

        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("fecha_objetivo", respuesta.data)
