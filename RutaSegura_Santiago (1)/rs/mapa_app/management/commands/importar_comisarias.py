from django.core.management.base import BaseCommand, CommandError

from mapa_app import views


class Command(BaseCommand):
    help = "Descarga todas las comisarías del Gran Santiago (OpenStreetMap) y las guarda en datos/comisarias.json."

    def handle(self, *args, **opciones):
        lista = views.obtener_comisarias(forzar=True)
        if lista is None:
            raise CommandError("No se pudo descargar. Revisa tu conexión a internet e inténtalo de nuevo.")
        self.stdout.write(self.style.SUCCESS(f"Listo: {len(lista)} comisarías guardadas en datos/comisarias.json."))
