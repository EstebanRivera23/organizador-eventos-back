from decimal import Decimal

from rest_framework.test import APITestCase

from .models import Organizador

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
