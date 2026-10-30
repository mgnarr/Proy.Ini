import difflib
import json
import math
import re
import unicodedata

from .comunas import CENTROS_COMUNAS
from .riesgo import distancia_m

TIPOS_SEGUROS = {
    'policia': {'nombre': 'Comisaría / Carabineros', 'filtros': []},
    'hospital': {'nombre': 'Hospital / Clínica', 'filtros': [('amenity', 'hospital'), ('amenity', 'clinic')]},
    'bomberos': {'nombre': 'Bomberos', 'filtros': [('amenity', 'fire_station')]},
    'mall': {'nombre': 'Centro comercial', 'filtros': [('shop', 'mall')]},
    'super': {'nombre': 'Supermercado', 'filtros': [('shop', 'supermarket')]},
    'metro': {'nombre': 'Estación de Metro', 'filtros': [('station', 'subway')]},
    'farmacia': {'nombre': 'Farmacia', 'filtros': [('amenity', 'pharmacy')]},
    'publico': {'nombre': 'Lugar público concurrido', 'filtros': []},
}
TIPOS_OTROS = ['hospital', 'bomberos', 'mall', 'super', 'metro', 'farmacia']

BBOX_SANTIAGO = (-33.70, -70.90, -33.28, -70.42)
PATRON_NOMBRE = "omisar[ií]a|Subcomisar|Tenencia de Carab|Ret[eé]n de Carab"

def normalizar(texto):
    texto = unicodedata.normalize('NFKD', texto or '').encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]', ' ', texto.lower())).strip()


def _dentro(lon, lat, anillo):
    adentro = False
    n = len(anillo)
    for i in range(n):
        x1, y1 = anillo[i]
        x2, y2 = anillo[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            adentro = not adentro
    return adentro


class Comunas:
    def __init__(self, ruta_geojson):
        with open(ruta_geojson, encoding='utf-8') as f:
            datos = json.load(f)
        self.poligonos = []
        for feat in datos['features']:
            for poli in feat['geometry']['coordinates']:
                self.poligonos.append((feat['properties']['comuna'], poli[0]))

    def comuna_de(self, lat, lon):
        for nombre, anillo in self.poligonos:
            if _dentro(lon, lat, anillo):
                return nombre
        nombre, d = min(((n, distancia_m(lat, lon, c[0], c[1])) for n, c in CENTROS_COMUNAS.items()),
                        key=lambda par: par[1])
        return nombre if d < 3000 else None

    def en_santiago(self, lat, lon):
        return self.comuna_de(lat, lon) is not None


class Calles:
    def __init__(self, paradas):
        self.items = []
        vocabulario = set()
        for nombre, lat, lon in paradas:
            limpio = re.sub(r'^[A-Za-z]{1,3}\d+[A-Za-z]?-', '', nombre or '').strip()
            if not limpio or limpio.lower().startswith('parada') and '/' not in limpio.replace('Parada /', ''):
                continue
            norm = normalizar(limpio)
            if not norm:
                continue
            self.items.append((limpio, norm, lat, lon))
            vocabulario.update(norm.split())
        self.vocabulario = sorted(vocabulario)

    @staticmethod
    def etiqueta(limpio):
        limpio = re.sub(r'^Parada\s*\d*\s*/\s*', '', limpio)
        limpio = re.sub(r'\s*/\s*esq\.?\s*', ' con ', limpio, flags=re.I)
        limpio = re.sub(r'^(Av\.|Avda\.|Avenida)\s*(?=\S)', 'Av. ', limpio)
        return limpio.strip()

    def _variantes(self, palabra):
        resultado = {palabra}
        if len(palabra) >= 4:
            resultado.update(difflib.get_close_matches(palabra, self.vocabulario, n=4, cutoff=0.78))
        return resultado

    def buscar(self, consulta, maximo=6):
        palabras = [w for w in normalizar(consulta).split() if w not in ('con', 'esq', 'esquina', 'y', 'e')]
        if not palabras:
            return []
        exactas = [p for p in palabras]
        encontrados = self._filtrar([{p} for p in exactas])
        if not encontrados:
            encontrados = self._filtrar([self._variantes(p) for p in palabras])
        vistos, salida = set(), []
        for limpio, norm, lat, lon, puntaje in sorted(encontrados, key=lambda t: (t[4], len(t[1]))):
            nombre = self.etiqueta(limpio)
            clave = normalizar(nombre)
            if clave in vistos:
                continue
            vistos.add(clave)
            salida.append({'nombre': nombre, 'lat': lat, 'lon': lon})
            if len(salida) >= maximo:
                break
        return salida

    def _filtrar(self, grupos):
        encontrados = []
        for limpio, norm, lat, lon in self.items:
            palabras_nombre = norm.split()
            puntaje = 0
            ok = True
            for k, grupo in enumerate(grupos):
                ultimo = k == len(grupos) - 1
                coincide = any(
                    (w == v) or (ultimo and w.startswith(v)) or (len(v) >= 4 and v in w and ultimo)
                    for v in grupo for w in palabras_nombre)
                if not coincide:
                    ok = False
                    break
                if palabras_nombre and any(w in grupo for w in palabras_nombre[:2]):
                    puntaje -= 1
            if ok:
                encontrados.append((limpio, norm, lat, lon, puntaje))
        return encontrados


def consulta_comisarias(bbox=BBOX_SANTIAGO):
    caja = f'({bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]})'
    return ('[out:json][timeout:90];('
            f'nwr["amenity"="police"]{caja};'
            f'nwr["name"~"{PATRON_NOMBRE}",i]["amenity"!~"."]{caja};'
            ');out center 3000;')


def categoria(nombre, tags):
    texto = (nombre + ' ' + tags.get('operator', '')).lower()
    if 'investigaciones' in texto or 'pdi' in texto.split():
        return 'PDI'
    return 'Comisaría / Carabineros'


def leer_comisarias(respuesta):
    lista = []
    for e in respuesta.get('elements', []):
        tags = e.get('tags', {})
        if 'lat' in e:
            y, x = e['lat'], e['lon']
        elif 'center' in e:
            y, x = e['center']['lat'], e['center']['lon']
        else:
            continue
        nombre = tags.get('name') or 'Comisaría (sin nombre)'
        if any(o['nombre'] == nombre and distancia_m(y, x, o['lat'], o['lon']) < 100 for o in lista):
            continue
        lista.append({'tipo': 'policia', 'categoria': categoria(nombre, tags), 'nombre': nombre,
                      'lat': round(y, 6), 'lon': round(x, 6)})
    return lista


def mas_cercanas(lista, lat, lon, cantidad=6):
    con_distancia = [dict(l, metros=round(distancia_m(lat, lon, l['lat'], l['lon']))) for l in lista]
    con_distancia.sort(key=lambda l: l['metros'])
    return con_distancia[:cantidad]


def consulta_otros(lat, lon, radio, tipos=TIPOS_OTROS):
    partes = []
    for t in tipos:
        for clave, valor in TIPOS_SEGUROS[t]['filtros']:
            for elemento in ('node', 'way'):
                partes.append(f'{elemento}["{clave}"="{valor}"](around:{int(radio)},{lat},{lon});')
    return '[out:json][timeout:25];(' + ''.join(partes) + ');out center 120;'


def _tipo_de(tags):
    if tags.get('amenity') in ('hospital', 'clinic'):
        return 'hospital'
    if tags.get('amenity') == 'fire_station':
        return 'bomberos'
    if tags.get('shop') == 'mall':
        return 'mall'
    if tags.get('shop') == 'supermarket':
        return 'super'
    if tags.get('station') == 'subway':
        return 'metro'
    if tags.get('amenity') == 'pharmacy':
        return 'farmacia'
    return None


def leer_otros(respuesta, lat, lon):
    lista, vistos = [], set()
    for e in respuesta.get('elements', []):
        tags = e.get('tags', {})
        tipo = _tipo_de(tags)
        if not tipo:
            continue
        if 'lat' in e:
            y, x = e['lat'], e['lon']
        elif 'center' in e:
            y, x = e['center']['lat'], e['center']['lon']
        else:
            continue
        nombre = tags.get('name') or TIPOS_SEGUROS[tipo]['nombre']
        clave = (nombre, round(y, 4), round(x, 4))
        if clave in vistos:
            continue
        vistos.add(clave)
        lista.append({'tipo': tipo, 'categoria': TIPOS_SEGUROS[tipo]['nombre'], 'nombre': nombre,
                      'lat': y, 'lon': x, 'metros': round(distancia_m(lat, lon, y, x))})
    lista.sort(key=lambda l: l['metros'])
    return lista


def consulta_otros_ruta(puntos, radio, tipos=TIPOS_OTROS):
    linea = ','.join(f'{lat:.5f},{lon:.5f}' for lat, lon in puntos)
    partes = []
    for t in tipos:
        for clave, valor in TIPOS_SEGUROS[t]['filtros']:
            for elemento in ('node', 'way'):
                partes.append(f'{elemento}["{clave}"="{valor}"](around:{int(radio)},{linea});')
    return '[out:json][timeout:25];(' + ''.join(partes) + ');out center 200;'


def distancia_a_segmento(lat, lon, a, b):
    k_lat, k_lon = 111320.0, 111320.0 * math.cos(math.radians(lat))
    px, py = (lon - a[1]) * k_lon, (lat - a[0]) * k_lat
    dx, dy = (b[1] - a[1]) * k_lon, (b[0] - a[0]) * k_lat
    largo2 = dx * dx + dy * dy
    t = 0 if largo2 == 0 else max(0, min(1, (px * dx + py * dy) / largo2))
    return math.hypot(px - t * dx, py - t * dy)


def distancia_a_ruta(lat, lon, puntos):
    return min(distancia_a_segmento(lat, lon, puntos[i], puntos[i + 1]) for i in range(len(puntos) - 1))


def cerca_de_ruta(lista, puntos, radio):
    resultado = []
    for l in lista:
        d = distancia_a_ruta(l['lat'], l['lon'], puntos)
        if d <= radio:
            resultado.append(dict(l, metros=round(d)))
    resultado.sort(key=lambda l: l['metros'])
    return resultado
