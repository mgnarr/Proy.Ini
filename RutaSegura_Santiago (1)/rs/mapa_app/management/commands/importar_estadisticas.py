import csv
import io
import json
import urllib.request
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from mapa_app.comunas import CENTROS_COMUNAS
from mapa_app.models import EstadisticaComuna, RegistroFuente
from mapa_app.riesgo import clave_comuna

COLUMNAS_COMUNA = ("comuna", "nombre_comuna", "territorio", "nombre")
COLUMNAS_DELITOS = ("delitos", "casos", "total", "cantidad", "valor", "frecuencia")
COLUMNAS_PERIODO = ("periodo", "año", "anio", "ano")
COLUMNAS_POBLACION = ("poblacion", "población", "habitantes")

def a_numero(texto):
    if isinstance(texto, (int, float)):
        return int(texto)
    texto = str(texto).strip().replace(" ", "")
    if not texto:
        return None
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif texto.count(".") > 1 or (texto.count(".") == 1 and len(texto.split(".")[1]) == 3):
        texto = texto.replace(".", "")
    try:
        return int(round(float(texto)))
    except ValueError:
        return None

def buscar(fila, nombres):
    for clave, valor in fila.items():
        if clave and clave.strip().lower() in nombres:
            return valor
    return None

def leer_texto(contenido):
    for codificacion in ("utf-8-sig", "latin-1"):
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue

def filas_desde_texto(texto):
    texto_limpio = texto.lstrip()
    if texto_limpio.startswith("[") or texto_limpio.startswith("{"):
        datos = json.loads(texto_limpio)
        if isinstance(datos, dict):
            for clave in ("data", "results", "resultados", "items", "datos"):
                if isinstance(datos.get(clave), list):
                    datos = datos[clave]
                    break
            else:
                raise CommandError("El JSON no es una lista de filas. Revisa su estructura.")
        return [f for f in datos if isinstance(f, dict)]
    muestra = texto.split("\n", 1)[0]
    separador = ";" if muestra.count(";") > muestra.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=separador))

class Command(BaseCommand):
    help = "Importa estadísticas de delitos por comuna (CEAD, Observatorio Público u otra fuente)."

    def add_arguments(self, parser):
        parser.add_argument("--archivo", help="Ruta de un archivo .csv o .json")
        parser.add_argument("--url", help="URL de un .csv o .json (por ejemplo, de la API del Observatorio Público)")
        parser.add_argument("--fuente", default="Sin especificar", help='Ej.: "CEAD" u "Observatorio Público"')
        parser.add_argument("--periodo", default="", help="Período de los datos si el archivo no lo trae (ej. 2025)")

    def handle(self, *args, **opciones):
        if not opciones["archivo"] and not opciones["url"]:
            raise CommandError("Indica --archivo RUTA o --url URL.")
        url = opciones["url"] or ""
        if opciones["archivo"]:
            ruta = Path(opciones["archivo"])
            if not ruta.exists():
                raise CommandError(f"No existe el archivo {ruta}")
            contenido = ruta.read_bytes()
        else:
            try:
                peticion = urllib.request.Request(url, headers={"User-Agent": settings.USER_AGENT})
                with urllib.request.urlopen(peticion, timeout=60) as respuesta:
                    contenido = respuesta.read()
            except OSError as error:
                raise CommandError(
                    f"No se pudo descargar {url} ({error}). Descarga el archivo a mano y usa --archivo.")

        try:
            filas = filas_desde_texto(leer_texto(contenido))
        except (ValueError, TypeError) as error:
            raise CommandError(f"No se pudo leer el archivo: {error}")
        if not filas:
            raise CommandError("El archivo no tiene filas.")

        acumulado = {}
        omitidas = 0
        for fila in filas:
            comuna = buscar(fila, COLUMNAS_COMUNA)
            delitos = a_numero(buscar(fila, COLUMNAS_DELITOS) or "")
            if not comuna or delitos is None:
                omitidas += 1
                continue
            periodo = str(buscar(fila, COLUMNAS_PERIODO) or opciones["periodo"] or "sin período").strip()
            poblacion = a_numero(buscar(fila, COLUMNAS_POBLACION) or "")
            clave = (clave_comuna(comuna), periodo)
            if clave not in acumulado:
                acumulado[clave] = {"comuna": str(comuna).strip(), "delitos": 0, "poblacion": poblacion}
            acumulado[clave]["delitos"] += delitos

        if not acumulado:
            columnas = ", ".join(str(c) for c in filas[0].keys())
            raise CommandError(
                "No se encontraron columnas de comuna y de cantidad de delitos. "
                f"Columnas del archivo: {columnas}. Renómbralas según datos/plantilla_estadisticas_comunales.csv.")

        periodos = sorted({p for _, p in acumulado})
        periodo_elegido = periodos[-1]
        with transaction.atomic():
            EstadisticaComuna.objects.all().delete()
            nuevas = [EstadisticaComuna(comuna=v["comuna"], comuna_clave=c, periodo=p, delitos=v["delitos"],
                                        poblacion=v["poblacion"], fuente=opciones["fuente"], url_fuente=url)
                      for (c, p), v in acumulado.items() if p == periodo_elegido]
            EstadisticaComuna.objects.bulk_create(nuevas)
            RegistroFuente.objects.update_or_create(clave="delitos", defaults={
                "nombre": opciones["fuente"], "version": "", "periodo": periodo_elegido,
                "url": url or str(opciones["archivo"]),
                "notas": "Estadísticas por COMUNA. No indican la ubicación exacta de los delitos."})

        sin_ubicacion = [n.comuna for n in nuevas if n.comuna_clave not in {clave_comuna(c) for c in CENTROS_COMUNAS}]
        self.stdout.write(self.style.SUCCESS(f"Importadas {len(nuevas)} comunas del período {periodo_elegido}."))
        if omitidas:
            self.stdout.write(f"Se omitieron {omitidas} filas sin comuna o sin cantidad válida.")
        if sin_ubicacion:
            self.stdout.write("Comunas sin ubicación en el mapa (no se dibujan): " + ", ".join(sin_ubicacion))
