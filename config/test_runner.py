from django.apps import apps
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings


class TablasLocalesTestRunner(DiscoverRunner):
    """
    Los modelos son managed = False porque las tablas viven en Supabase.
    Para las pruebas se crean esas mismas tablas en la base temporal.
    """

    def setup_test_environment(self, **kwargs):
        super().setup_test_environment(**kwargs)
        self._sin_migraciones = override_settings(MIGRATION_MODULES={"api": None})
        self._sin_migraciones.enable()
        self._modelos_externos = [
            modelo for modelo in apps.get_models() if not modelo._meta.managed
        ]
        for modelo in self._modelos_externos:
            modelo._meta.managed = True

    def teardown_test_environment(self, **kwargs):
        for modelo in self._modelos_externos:
            modelo._meta.managed = False
        self._sin_migraciones.disable()
        super().teardown_test_environment(**kwargs)
