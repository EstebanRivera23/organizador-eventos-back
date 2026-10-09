from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APITestCase

from .models import Organizador, Subtarea

URL_LIMITE = "/api/organizador/limite-diario/"


class ApiTestCase(APITestCase):
    def entrar(self, email):
        """Crea la cuenta (o entra si ya existe) y deja el token en el cliente."""
        self.client.credentials()
        datos = {"email": email, "password": "prueba123"}
        if not Organizador.objects.filter(email=email).exists():
            respuesta = self.client.post(
                "/api/registro/", {**datos, "nombre": "Organizador de prueba"}, format="json"
            )
            self.assertEqual(respuesta.status_code, 201, respuesta.data)
        else:
            respuesta = self.client.post("/api/login/", datos, format="json")
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        return Organizador.objects.get(email=email)

    def crear_evento(self, nombre="Boda de prueba", dia="2030-01-15"):
        respuesta = self.client.post(
            "/api/eventos/",
            {
                "nombre": nombre,
                "tipo": "boda",
                "cliente_contacto": "Cliente de prueba",
                "fecha_hora": f"{dia}T18:00:00-05:00",
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


class ResolucionDeConflictoTests(ApiTestCase):
    """KAN-50: lo que trae el 409 para resolver, y la carga recalculada."""

    def setUp(self):
        self.entrar("prueba1@correo.com")
        # El evento es el 15 de enero: no se sugieren días después.
        self.evento = self.crear_evento()

    def fechas(self, respuesta):
        return [str(s["fecha"]) for s in respuesta.data["conflicto"]["fechas_sugeridas"]]

    def test_sugiere_los_dias_mas_cercanos_donde_cabe(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 409)
        # A un día de distancia están el 9 y el 11; a dos, el 12 (va primero el día posterior).
        self.assertEqual(self.fechas(respuesta), ["2030-01-09", "2030-01-11", "2030-01-12"])
        self.assertEqual(
            respuesta.data["conflicto"]["fechas_sugeridas"][0]["horas_planificadas"], "2.00"
        )
        self.assertEqual(respuesta.data["conflicto"]["horas_disponibles"], "1.00")

    def test_no_sugiere_dias_que_tambien_quedarian_llenos(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        self.crear_gestion(self.evento, "Confirmar catering", date(2030, 1, 11), 5)
        self.crear_gestion(self.evento, "Enviar invitaciones", date(2030, 1, 9), 4)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        # El 11 no cabe (5 + 2); el 9 sí, justo en el límite (4 + 2).
        self.assertEqual(self.fechas(respuesta), ["2030-01-08", "2030-01-09", "2030-01-12"])
        sugeridas = respuesta.data["conflicto"]["fechas_sugeridas"]
        self.assertEqual(sugeridas[1]["horas_planificadas"], "6.00")

    def test_no_sugiere_dias_despues_del_evento(self):
        self.crear_gestion(self.evento, "Reservar salón", date(2030, 1, 15), 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=date(2030, 1, 15))

        self.assertEqual(self.fechas(respuesta), ["2030-01-12", "2030-01-13", "2030-01-14"])

    def test_no_sugiere_dias_que_ya_pasaron(self):
        hoy = timezone.localdate()
        evento = self.crear_evento("Cumpleaños de prueba", dia=str(hoy + timedelta(days=20)))
        self.crear_gestion(evento, "Reservar salón", hoy, 5)
        proveedores = self.crear_gestion(evento, "Buscar proveedores", hoy + timedelta(days=5), 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=hoy)

        esperadas = [str(hoy + timedelta(days=d)) for d in (1, 2, 3)]
        self.assertEqual(self.fechas(respuesta), esperadas)

    def test_sin_sugerencias_si_la_gestion_sola_pasa_el_limite(self):
        self.client.put(URL_LIMITE, {"limite_horas_dia": 2}, format="json")
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 1)
        grande = self.crear_gestion(self.evento, "Montaje completo", date(2030, 1, 5), 3)

        respuesta = self.cambiar_gestion(grande, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["conflicto"]["fechas_sugeridas"], [])
        self.assertEqual(respuesta.data["conflicto"]["horas_disponibles"], "1.00")

    def test_dia_lleno_tiene_cero_horas_disponibles(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 4)
        self.crear_gestion(self.evento, "Confirmar catering", DIA_X, 3)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)

        self.assertEqual(respuesta.data["conflicto"]["horas_disponibles"], "0.00")

    def test_mover_a_una_fecha_sugerida_resuelve_y_devuelve_la_carga(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)
        conflicto = self.cambiar_gestion(proveedores, fecha_objetivo=DIA_X)
        sugerida = self.fechas(conflicto)[0]

        respuesta = self.cambiar_gestion(proveedores, fecha_objetivo=sugerida)

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(str(respuesta.data["fecha_objetivo"]), sugerida)
        self.assertEqual(str(respuesta.data["carga_dia"]["fecha"]), sugerida)
        self.assertEqual(respuesta.data["carga_dia"]["horas_planificadas"], "2.00")
        self.assertEqual(respuesta.data["carga_dia"]["limite_horas_dia"], "6.00")

    def test_reducir_resuelve_y_devuelve_la_carga_del_dia(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(
            proveedores, fecha_objetivo=DIA_X, horas_estimadas=1
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["carga_dia"]["horas_planificadas"], "6.00")

    def test_reducir_poco_sigue_en_conflicto_con_cifras_nuevas(self):
        self.crear_gestion(self.evento, "Reservar salón", DIA_X, 5)
        proveedores = self.crear_gestion(self.evento, "Buscar proveedores", date(2030, 1, 5), 2)

        respuesta = self.cambiar_gestion(
            proveedores, fecha_objetivo=DIA_X, horas_estimadas=1.5
        )

        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(
            respuesta.data["detail"], "Quedarías con 6.5h planificadas (límite 6h)"
        )


class DocumentacionTests(APITestCase):
    def test_el_esquema_incluye_los_endpoints_del_sprint_3(self):
        respuesta = self.client.get("/api/schema/", HTTP_ACCEPT="application/json")

        self.assertEqual(respuesta.status_code, 200)
        rutas = respuesta.json()["paths"]
        self.assertIn("/api/organizador/limite-diario/", rutas)
        self.assertIn("409", rutas["/api/subtareas/{id}/"]["patch"]["responses"])

    def test_la_pagina_de_swagger_abre_sin_sesion(self):
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)


CUENTA = {"nombre": "Ana Gómez", "email": "ana@correo.com", "password": "secreto123"}


class RegistroTests(APITestCase):
    def registrar(self, **cambios):
        return self.client.post("/api/registro/", {**CUENTA, **cambios}, format="json")

    def test_crea_la_cuenta_y_deja_la_sesion_iniciada(self):
        respuesta = self.registrar()

        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["organizador"]["nombre"], "Ana Gómez")
        self.assertEqual(respuesta.data["organizador"]["email"], "ana@correo.com")
        self.assertNotIn("password", respuesta.data["organizador"])

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {respuesta.data['token']}")
        self.assertEqual(self.client.get("/api/organizador/me/").data["email"], "ana@correo.com")
        self.assertEqual(
            Decimal(self.client.get(URL_LIMITE).data["limite_horas_dia"]), Decimal("6")
        )

    def test_la_contrasena_no_se_guarda_en_texto(self):
        self.registrar()

        guardada = Organizador.objects.get(email="ana@correo.com").password_hash
        self.assertNotEqual(guardada, "secreto123")
        self.assertNotIn("secreto123", guardada)

    def test_el_correo_se_guarda_en_minusculas(self):
        respuesta = self.registrar(email="  Ana@Correo.COM ")

        self.assertEqual(respuesta.status_code, 201)
        self.assertTrue(Organizador.objects.filter(email="ana@correo.com").exists())

    def test_correo_repetido_no_crea_otra_cuenta(self):
        self.registrar()

        respuesta = self.registrar(email="ANA@correo.com", nombre="Otra persona")

        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(respuesta.data["email"], ["Ya existe una cuenta con este correo."])
        self.assertEqual(Organizador.objects.count(), 1)
        self.assertEqual(Organizador.objects.get().nombre, "Ana Gómez")

    def test_campos_obligatorios(self):
        respuesta = self.client.post("/api/registro/", {}, format="json")

        self.assertEqual(respuesta.status_code, 400)
        for campo in ("nombre", "email", "password"):
            self.assertEqual(respuesta.data[campo], ["Este campo es obligatorio."])
        self.assertEqual(Organizador.objects.count(), 0)

    def test_validaciones_de_cada_campo(self):
        casos = [
            ({"nombre": "   "}, "nombre", "Este campo es obligatorio."),
            ({"email": "ana-sin-arroba"}, "email", "Escribe un correo válido"),
            ({"password": "12345"}, "password", "al menos 6 caracteres"),
        ]
        for cambios, campo, mensaje in casos:
            respuesta = self.registrar(**cambios)
            self.assertEqual(respuesta.status_code, 400, cambios)
            self.assertIn(mensaje, respuesta.data[campo][0])
        self.assertEqual(Organizador.objects.count(), 0)


class LoginTests(APITestCase):
    def setUp(self):
        self.client.post("/api/registro/", CUENTA, format="json")

    def entrar(self, email, password):
        return self.client.post(
            "/api/login/", {"email": email, "password": password}, format="json"
        )

    def test_entra_con_la_cuenta_registrada(self):
        respuesta = self.entrar("Ana@correo.com", "secreto123")

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["organizador"]["nombre"], "Ana Gómez")
        self.assertTrue(respuesta.data["token"])

    def test_un_correo_sin_cuenta_ya_no_crea_la_cuenta(self):
        respuesta = self.entrar("nuevo@correo.com", "secreto123")

        self.assertEqual(respuesta.status_code, 401)
        self.assertEqual(respuesta.data["detail"], "Credenciales inválidas.")
        self.assertFalse(Organizador.objects.filter(email="nuevo@correo.com").exists())

    def test_no_revela_si_el_correo_existe(self):
        mala_clave = self.entrar("ana@correo.com", "otra-clave")
        sin_cuenta = self.entrar("nadie@correo.com", "otra-clave")

        self.assertEqual(mala_clave.status_code, 401)
        self.assertEqual(mala_clave.status_code, sin_cuenta.status_code)
        self.assertEqual(mala_clave.data, sin_cuenta.data)

    def test_una_cuenta_sin_contrasena_no_se_puede_tomar(self):
        Organizador.objects.create(nombre="Cuenta vieja", email="vieja@correo.com")

        respuesta = self.entrar("vieja@correo.com", "cualquiera123")

        self.assertEqual(respuesta.status_code, 401)
        self.assertFalse(Organizador.objects.get(email="vieja@correo.com").password_hash)

    def test_campos_obligatorios(self):
        self.assertIn("email", self.entrar("", "secreto123").data)
        self.assertIn("password", self.entrar("ana@correo.com", "").data)
