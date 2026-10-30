import json
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mapa_app import gtfs
from mapa_app.models import Parada, Recorrido, RegistroFuente, SecuenciaParada, Sentido

class Command(BaseCommand):
    help = "Descarga e importa el GTFS oficial del DTPM (recorridos, paraderos y trazados de micros)."

    def add_arguments(self, parser):
        parser.add_argument("--zip", help="Ruta de un GTFS .zip ya descargado")
        parser.add_argument("--url", help="URL directa del GTFS .zip")
        parser.add_argument("--si-falta", action="store_true", dest="si_falta",
                            help="No hace nada si el GTFS ya está importado")

    def handle(self, *args, **opciones):
        if opciones["si_falta"] and Recorrido.objects.exists():
            self.stdout.write("El GTFS ya está importado. Para actualizarlo ejecuta: python manage.py importar_gtfs")
            return
        if opciones["zip"]:
            ruta = Path(opciones["zip"])
            url = ""
            if not ruta.exists():
                raise CommandError(f"No existe el archivo {ruta}")
        elif not opciones["url"] and sorted(Path(settings.GTFS_CARPETA).glob("GTFS_*.zip")):
            ruta = sorted(Path(settings.GTFS_CARPETA).glob("GTFS_*.zip"))[-1]
            url = ""
            self.stdout.write(f"Usando el GTFS incluido en el proyecto: {ruta.name}")
        else:
            url = opciones["url"] or self.buscar_url_vigente()
            ruta = self.descargar(url)

        self.stdout.write("Leyendo el GTFS (puede tardar varios minutos)...")
        try:
            datos = gtfs.leer_gtfs(ruta, aviso=self.stdout.write)
        except (ValueError, OSError) as error:
            raise CommandError(str(error))

        self.guardar(datos, url or str(ruta), ruta.name)
        lugares = gtfs.lugares_seguros(ruta)
        with open(Path(settings.BASE_DIR) / "datos" / "lugares_seguros.json", "w", encoding="utf-8") as f:
            json.dump(lugares, f, ensure_ascii=False, indent=1)
        self.stdout.write(f"Lugares seguros del GTFS guardados: {len(lugares)}.")
        self.stdout.write(self.style.SUCCESS(
            f"Listo: {len(datos['rutas'])} recorridos, {len(datos['sentidos'])} sentidos, "
            f"{len(datos['paradas'])} paraderos."))

    def buscar_url_vigente(self):
        self.stdout.write(f"Buscando el GTFS vigente en {settings.GTFS_PAGINA_DTPM} ...")
        try:
            peticion = urllib.request.Request(settings.GTFS_PAGINA_DTPM, headers={"User-Agent": settings.USER_AGENT})
            with urllib.request.urlopen(peticion, timeout=30) as respuesta:
                html = respuesta.read().decode("utf-8", errors="ignore")
            url = gtfs.encontrar_url_vigente(html)
            if url:
                return url
            self.stdout.write("No se encontró el enlace en la página. Se usa la URL de respaldo.")
        except OSError as error:
            self.stdout.write(f"No se pudo abrir la página del DTPM ({error}). Se usa la URL de respaldo.")
        return settings.GTFS_URL_RESPALDO

    def descargar(self, url):
        carpeta = Path(settings.GTFS_CARPETA)
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / url.rstrip("/").split("/")[-1]
        self.stdout.write(f"Descargando {url}")
        try:
            peticion = urllib.request.Request(url, headers={"User-Agent": settings.USER_AGENT})
            with urllib.request.urlopen(peticion, timeout=60) as respuesta, open(destino, "wb") as salida:
                while True:
                    bloque = respuesta.read(1024 * 1024)
                    if not bloque:
                        break
                    salida.write(bloque)
        except OSError as error:
            raise CommandError(
                f"No se pudo descargar el GTFS ({error}). Descárgalo manualmente desde "
                f"{settings.GTFS_PAGINA_DTPM} y usa: python manage.py importar_gtfs --zip RUTA_DEL_ZIP")
        self.stdout.write(f"Guardado en {destino}")
        return destino

    @transaction.atomic
    def guardar(self, datos, origen, nombre_archivo):
        SecuenciaParada.objects.all().delete()
        Sentido.objects.all().delete()
        Recorrido.objects.all().delete()
        Parada.objects.all().delete()

        Parada.objects.bulk_create(
            [Parada(stop_id=p["stop_id"], nombre=p["nombre"], lat=p["lat"], lon=p["lon"]) for p in datos["paradas"]],
            batch_size=2000)
        Recorrido.objects.bulk_create(
            [Recorrido(route_id=r["route_id"], numero=r["numero"], nombre=r["nombre"], color=r["color"])
             for r in datos["rutas"]], batch_size=1000)

        recorridos = {r.route_id: r for r in Recorrido.objects.all()}
        paradas = {p.stop_id: p for p in Parada.objects.all()}
        secuencias = []
        for s in datos["sentidos"]:
            sentido = Sentido.objects.create(
                recorrido=recorridos[s["route_id"]], direction_id=s["direction_id"], destino=s["destino"],
                trazado=json.dumps(s["trazado"]), n_viajes=s["n_viajes"])
            for orden, fila in enumerate(s["secuencia"]):
                secuencias.append(SecuenciaParada(
                    sentido=sentido, parada=paradas[fila["stop_id"]], orden=orden, segundos=fila["segundos"]))
        SecuenciaParada.objects.bulk_create(secuencias, batch_size=5000)

        RegistroFuente.objects.update_or_create(clave="gtfs", defaults={
            "nombre": "GTFS RED Movilidad (DTPM)",
            "version": datos["version"] or nombre_archivo,
            "periodo": "Servicio de referencia: " + (datos["servicio_referencia"] or "sin dato"),
            "url": origen,
            "notas": "Horarios programados del GTFS. No es la ubicación en tiempo real de las micros.",
        })
