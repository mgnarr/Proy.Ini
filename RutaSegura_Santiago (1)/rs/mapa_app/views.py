import io
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.management import call_command
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from . import gtfs, lugares, riesgo, transporte
from .comunas import CENTROS_COMUNAS
from .models import (BotonPanico, EstadisticaComuna, Parada, RegistroFuente, SecuenciaParada,
                     Sentido, Recorrido, SolicitudRuta)

def cargar_crimenes_santiago():
    ruta_json = os.path.join(settings.BASE_DIR, 'datos', 'crimenes_santiago.json')
    with open(ruta_json, 'r', encoding='utf-8') as f:
        return json.load(f)

def cargar_zonas():
    filas = list(EstadisticaComuna.objects.values(
        'comuna', 'comuna_clave', 'delitos', 'poblacion', 'periodo', 'fuente'))
    if filas:
        zonas, _ = riesgo.zonas_desde_estadisticas(filas, CENTROS_COMUNAS)
        return zonas, 'comunal'
    return riesgo.zonas_de_ejemplo(cargar_crimenes_santiago()), 'ejemplo'

def info_fuente(clave):
    registro = RegistroFuente.objects.filter(clave=clave).first()
    if not registro:
        return None
    return {
        'nombre': registro.nombre,
        'version': registro.version,
        'periodo': registro.periodo,
        'url': registro.url,
        'notas': registro.notas,
        'actualizado': registro.fecha_importacion.strftime('%d-%m-%Y %H:%M'),
    }

def leer_float(request, nombre):
    return float(request.GET.get(nombre))

def leer_puntos(request):
    try:
        return (leer_float(request, 'lat1'), leer_float(request, 'lon1'),
                leer_float(request, 'lat2'), leer_float(request, 'lon2'))
    except (TypeError, ValueError):
        return None

def error_parametros():
    return JsonResponse({'exito': False, 'error': 'Parámetros inválidos: se esperan lat1, lon1, lat2 y lon2.'},
                        status=400)

def registrar_busqueda(request, puntos, medio, opciones):
    if not opciones:
        return
    mejor = next((o for o in opciones if o.get('mas_segura')), opciones[0])
    SolicitudRuta.objects.create(
        origen_lat=puntos[0], origen_lon=puntos[1], destino_lat=puntos[2], destino_lon=puntos[3],
        origen_texto=request.GET.get('origen', '')[:200], destino_texto=request.GET.get('destino', '')[:200],
        medio_transporte=medio, riesgo_calculado=mejor['indice_riesgo'], tiempo_estimado_min=mejor['tiempo_min'])

def index_view(request):
    iniciar_descarga_comisarias()
    return render(request, 'mapa_app/index.html')

def api_zonas(request):
    zonas, modo = cargar_zonas()
    return JsonResponse({'modo': modo, 'zonas': zonas, 'fuente': info_fuente('delitos')})

IMPORTACION = {'activa': False, 'error': ''}


def _importar_en_segundo_plano():
    try:
        call_command('importar_gtfs', stdout=io.StringIO())
        IMPORTACION['error'] = ''
    except Exception as error:
        IMPORTACION['error'] = str(error)
    finally:
        IMPORTACION['activa'] = False


def iniciar_importacion_gtfs():
    if IMPORTACION['activa'] or Recorrido.objects.exists():
        return
    IMPORTACION['activa'] = True
    IMPORTACION['error'] = ''
    threading.Thread(target=_importar_en_segundo_plano, daemon=True).start()


def api_fuentes(request):
    _, modo = cargar_zonas()
    if not Recorrido.objects.exists() and not request.GET.get('sin_importar'):
        iniciar_importacion_gtfs()
    return JsonResponse({
        'modo_riesgo': modo,
        'delitos': info_fuente('delitos'),
        'gtfs': info_fuente('gtfs'),
        'gtfs_recorridos': Recorrido.objects.count(),
        'gtfs_paraderos': Parada.objects.count(),
        'importando': IMPORTACION['activa'],
        'error_importacion': IMPORTACION['error'],
    })


CACHE_LUGARES = {}

def _pedir_json(url):
    peticion = urllib.request.Request(url, headers={'User-Agent': settings.USER_AGENT})
    with urllib.request.urlopen(peticion, timeout=8) as respuesta:
        return json.loads(respuesta.read().decode('utf-8'))

COMUNAS = lugares.Comunas(os.path.join(settings.BASE_DIR, 'datos', 'comunas_santiago.geojson'))
CALLES = {'cantidad': -1, 'objeto': None}


def en_santiago(lat, lon):
    return COMUNAS.en_santiago(lat, lon)


def calles_locales():
    cantidad = Parada.objects.count()
    if CALLES['cantidad'] != cantidad:
        CALLES['objeto'] = lugares.Calles(Parada.objects.values_list('nombre', 'lat', 'lon'))
        CALLES['cantidad'] = cantidad
    return CALLES['objeto']


def _corto(partes):
    resultado = []
    for p in partes:
        if p and p not in resultado:
            resultado.append(p)
    return ', '.join(resultado)


def buscar_nominatim(q):
    parametros = urllib.parse.urlencode({
        'q': q, 'format': 'json', 'limit': 8, 'countrycodes': 'cl', 'addressdetails': 1,
        'viewbox': '-70.90,-33.28,-70.42,-33.70', 'bounded': 1,
    })
    try:
        datos = _pedir_json(f'{settings.NOMINATIM_URL}?{parametros}')
    except Exception:
        return None
    resultados = []
    for d in datos:
        a = d.get('address', {})
        calle = a.get('road') or a.get('pedestrian') or a.get('footway') or a.get('path') or ''
        if calle and a.get('house_number'):
            calle += ' ' + a['house_number']
        lugar = d.get('name') or ''
        if lugar == a.get('road'):
            lugar = ''
        zona = a.get('suburb') or a.get('city_district') or a.get('neighbourhood') or a.get('city') or a.get('town') or ''
        nombre = _corto([lugar, calle, zona]) or d['display_name'].split(',')[0]
        if 'Metropolitana' not in a.get('state', 'Metropolitana') or not en_santiago(float(d['lat']), float(d['lon'])):
            continue
        resultados.append({'nombre': nombre, 'lat': float(d['lat']), 'lon': float(d['lon'])})
    return resultados


def buscar_photon(q):
    parametros = urllib.parse.urlencode({
        'q': q, 'limit': 8, 'lat': -33.45, 'lon': -70.65, 'bbox': '-70.90,-33.70,-70.42,-33.28'})
    try:
        datos = _pedir_json(f"{settings.PHOTON_URL}?{parametros}")
    except Exception:
        return None
    resultados = []
    for f in datos.get('features', []):
        p, (lon, lat) = f['properties'], f['geometry']['coordinates']
        if p.get('countrycode', 'CL') != 'CL':
            continue
        calle = p.get('street') or ''
        if calle and p.get('housenumber'):
            calle += ' ' + p['housenumber']
        nombre_lugar = p.get('name') or ''
        if nombre_lugar == p.get('street'):
            nombre_lugar = ''
        zona = p.get('district') or p.get('locality') or p.get('city') or ''
        if not calle and not nombre_lugar:
            continue
        if 'Metropolitan' not in p.get('state', 'Metropolitan') and 'Metropolitana' not in p.get('state', ''):
            continue
        if not en_santiago(float(lat), float(lon)):
            continue
        resultados.append({'nombre': _corto([nombre_lugar, calle, zona]), 'lat': float(lat), 'lon': float(lon)})
    return resultados


def buscar_ambos(q):
    resultados = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futuros = [pool.submit(buscar_photon, q), pool.submit(buscar_nominatim, q)]
        respuestas = [f.result() for f in futuros]
    if all(r is None for r in respuestas) and not calles_locales().buscar(q, maximo=1):
        return None
    final = []
    locales = calles_locales().buscar(q, maximo=4)
    for lista in [locales] + respuestas:
        for r in lista or []:
            repetido = any(abs(r['lat'] - o['lat']) < 0.0007 and abs(r['lon'] - o['lon']) < 0.0007
                           for o in final) or r['nombre'].lower() in resultados
            if not repetido:
                resultados[r['nombre'].lower()] = True
                final.append(r)
    return final[:9]


def api_buscar_lugar(request):
    q = request.GET.get('q', '').strip()
    if len(q) < 3:
        return JsonResponse({'resultados': []})
    if q.lower() in CACHE_LUGARES:
        return JsonResponse({'resultados': CACHE_LUGARES[q.lower()]})

    resultados = buscar_ambos(q)
    if resultados is None:
        return JsonResponse({'resultados': [], 'error': 'No se pudo consultar el buscador de direcciones.'},
                            status=502)
    if len(CACHE_LUGARES) > 300:
        CACHE_LUGARES.clear()
    CACHE_LUGARES[q.lower()] = resultados
    return JsonResponse({'resultados': resultados})

def pedir_rutas_osrm(medio, puntos):
    coords = ';'.join(f'{lon},{lat}' for lat, lon in puntos)
    for base in settings.RUTEO_URLS[medio]:
        try:
            datos = _pedir_json(f"{base}/{coords}?overview=full&geometries=geojson&alternatives=true")
            if datos.get('code') == 'Ok' and datos.get('routes'):
                return datos['routes']
        except Exception:
            continue
    return []

def es_distinta(ruta, existentes):
    medio = ruta['geometry']['coordinates'][len(ruta['geometry']['coordinates']) // 2]
    for otra in existentes:
        otro_medio = otra['geometry']['coordinates'][len(otra['geometry']['coordinates']) // 2]
        cerca = riesgo.distancia_m(medio[1], medio[0], otro_medio[1], otro_medio[0]) < 80
        if abs(ruta['distance'] - otra['distance']) < 60 and cerca:
            return False
    return True

def api_calcular_ruta(request):
    puntos = leer_puntos(request)
    if puntos is None:
        return error_parametros()
    lat1, lon1, lat2, lon2 = puntos
    medio = request.GET.get('medio', 'peaton')
    if medio not in settings.RUTEO_URLS:
        return JsonResponse({'exito': False, 'error': 'Medio no válido (peaton o auto).'}, status=400)

    rutas = pedir_rutas_osrm(medio, [(lat1, lon1), (lat2, lon2)])

    if rutas and len(rutas) < 3:
        medio_lat, medio_lon = (lat1 + lat2) / 2, (lon1 + lon2) / 2
        dx, dy = lon2 - lon1, lat2 - lat1
        largo = max((dx ** 2 + dy ** 2) ** 0.5, 1e-9)
        for signo in (1, -1):
            wp = (medio_lat + signo * (dx / largo) * 0.0065, medio_lon - signo * (dy / largo) * 0.0065)
            for r in pedir_rutas_osrm(medio, [(lat1, lon1), wp, (lat2, lon2)])[:1]:
                if es_distinta(r, rutas):
                    rutas.append(r)

    zonas, modo = cargar_zonas()
    opciones = []
    for r in rutas:
        coords = [[p[1], p[0]] for p in r['geometry']['coordinates']]
        evaluacion = riesgo.evaluar_ruta(coords, zonas)
        distancia = round(r['distance'])
        if medio == 'peaton':
            tiempo = max(1, round(distancia / transporte.M_POR_MIN_CAMINANDO))
        else:
            tiempo = max(1, round(r['duration'] / 60))
        opciones.append({
            'coordenadas': coords,
            'distancia_m': distancia,
            'tiempo_min': tiempo,
            'indice_riesgo': evaluacion['indice_riesgo'],
            'nivel_riesgo': evaluacion['nivel_riesgo'],
            'pct_zona_alta': evaluacion['pct_zona_alta'],
            'zonas_en_ruta': evaluacion['zonas_en_ruta'],
            'puntaje_riesgo': evaluacion['indice_riesgo'],
            'nivel_seguridad': {'Bajo': 'Alta', 'Medio': 'Media', 'Alto': 'Baja'}[evaluacion['nivel_riesgo']],
            'zonas_peligrosas_en_ruta': evaluacion['zonas_en_ruta'],
        })

    opciones.sort(key=lambda o: (o['indice_riesgo'], o['tiempo_min']))
    riesgo.marcar_mas_segura(opciones)
    if opciones:
        mas_rapida = min(opciones, key=lambda o: o['tiempo_min'])
        for numero, o in enumerate(opciones, start=1):
            o['titulo'] = f'Alternativa {numero}'
            o['mas_rapida'] = o is mas_rapida
    registrar_busqueda(request, puntos, medio, opciones)

    return JsonResponse({
        'exito': len(opciones) > 0,
        'medio': medio,
        'modo_riesgo': modo,
        'opciones': opciones,
        'mensaje': '' if opciones else 'No se pudo obtener rutas del servicio externo. Revisa tu conexión a internet.',
    })

def api_transporte(request):
    puntos = leer_puntos(request)
    if puntos is None:
        return error_parametros()
    lat1, lon1, lat2, lon2 = puntos
    origen, destino = (lat1, lon1), (lat2, lon2)

    if not Sentido.objects.exists():
        return JsonResponse({
            'exito': False, 'gtfs_disponible': False, 'opciones': [],
            'mensaje': 'Todavía no se importó el GTFS. Ejecuta: python manage.py importar_gtfs'})

    d_lat = transporte.RADIO_CAMINATA / riesgo.METROS_POR_GRADO_LAT
    d_lon = transporte.RADIO_CAMINATA / riesgo.METROS_POR_GRADO_LON
    candidatas = {}
    for lat, lon in (origen, destino):
        for p in Parada.objects.filter(lat__range=(lat - d_lat, lat + d_lat), lon__range=(lon - d_lon, lon + d_lon)):
            candidatas[p.id] = {'id': p.id, 'nombre': p.nombre, 'lat': p.lat, 'lon': p.lon}

    ids_sentidos = set(SecuenciaParada.objects.filter(parada_id__in=list(candidatas))
                       .values_list('sentido_id', flat=True))
    secuencias = {}
    filas = (SecuenciaParada.objects.filter(sentido_id__in=ids_sentidos)
             .select_related('parada').order_by('sentido_id', 'orden'))
    for fila in filas:
        secuencias.setdefault(fila.sentido_id, []).append({
            'parada_id': fila.parada_id, 'nombre': fila.parada.nombre, 'lat': fila.parada.lat,
            'lon': fila.parada.lon, 'segundos': fila.segundos, 'codigo': fila.parada.stop_id})
    sentidos = {s.id: {'sentido_id': s.id, 'numero': s.recorrido.numero, 'destino': s.destino,
                       'color': s.recorrido.color, 'n_viajes': s.n_viajes}
                for s in Sentido.objects.filter(id__in=ids_sentidos).select_related('recorrido')}

    alternativas = transporte.buscar_alternativas(origen, destino, list(candidatas.values()), secuencias, sentidos)

    zonas, modo = cargar_zonas()
    trazados = {s.id: json.loads(s.trazado or '[]') for s in Sentido.objects.filter(
        id__in={t['sentido_id'] for a in alternativas for t in a['tramos']})}
    for a in alternativas:
        evaluacion = riesgo.evaluar_ruta(transporte.puntos_de_alternativa(origen, destino, a), zonas)
        a.update({
            'indice_riesgo': evaluacion['indice_riesgo'], 'nivel_riesgo': evaluacion['nivel_riesgo'],
            'pct_zona_alta': evaluacion['pct_zona_alta'], 'zonas_en_ruta': evaluacion['zonas_en_ruta'],
            'titulo': ' + '.join('Micro ' + t['micro'] for t in a['tramos']),
        })
        a['distancia_m'] = 0
        for t in a['tramos']:
            corte = transporte.recortar_trazado(trazados.get(t['sentido_id'], []), t['sube'], t['baja'])
            t['usa_trazado_gtfs'] = bool(corte)
            t['trazado'] = corte or [[p['lat'], p['lon']] for p in t['paradas']]
            a['distancia_m'] += transporte.largo_m(t['trazado'])
        a['distancia_m'] += a['caminata_m']
    riesgo.marcar_mas_segura(alternativas)
    if alternativas:
        mas_rapida = min(alternativas, key=lambda a: a['tiempo_min'])
        for a in alternativas:
            a['mas_rapida'] = a is mas_rapida
    registrar_busqueda(request, puntos, 'micro', alternativas)

    return JsonResponse({
        'exito': len(alternativas) > 0, 'gtfs_disponible': True, 'modo_riesgo': modo, 'opciones': alternativas,
        'mensaje': '' if alternativas else (
            'No se encontraron micros con a lo más un transbordo entre paraderos a menos de '
            f'{transporte.RADIO_CAMINATA} m del origen y del destino.'),
    })

def api_micros(request):
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'recorridos': []})
    lista = []
    for r in Recorrido.objects.filter(numero__istartswith=q).order_by('numero')[:15]:
        lista.append({
            'numero': r.numero, 'nombre': r.nombre,
            'sentidos': [{'id': s.id, 'destino': s.destino} for s in r.sentidos.all()]})
    return JsonResponse({'recorridos': lista})

def api_sentido(request, sentido_id):
    s = get_object_or_404(Sentido.objects.select_related('recorrido'), id=sentido_id)
    paradas = [{'nombre': f.parada.nombre, 'lat': f.parada.lat, 'lon': f.parada.lon}
               for f in s.secuencia.select_related('parada')]
    return JsonResponse({
        'numero': s.recorrido.numero, 'destino': s.destino, 'color': s.recorrido.color,
        'trazado': json.loads(s.trazado or '[]'), 'paradas': paradas})

def api_paraderos(request):
    try:
        sur, oeste = float(request.GET['sur']), float(request.GET['oeste'])
        norte, este = float(request.GET['norte']), float(request.GET['este'])
    except (KeyError, ValueError):
        return JsonResponse({'paraderos': []}, status=400)
    consulta = Parada.objects.filter(lat__range=(sur, norte), lon__range=(oeste, este))[:400]
    return JsonResponse({'paraderos': [
        {'id': p.id, 'codigo': p.stop_id, 'nombre': p.nombre, 'lat': p.lat, 'lon': p.lon} for p in consulta]})

def api_parada(request, parada_id):
    p = get_object_or_404(Parada, id=parada_id)
    numeros = sorted(set(SecuenciaParada.objects.filter(parada=p).values_list('sentido__recorrido__numero', flat=True)))
    return JsonResponse({'nombre': p.nombre, 'codigo': p.stop_id, 'micros': numeros})

def api_historial(request):
    lista = []
    for s in SolicitudRuta.objects.order_by('-fecha_hora')[:8]:
        lista.append({
            'origen_texto': s.origen_texto or f'{s.origen_lat:.4f}, {s.origen_lon:.4f}',
            'destino_texto': s.destino_texto or f'{s.destino_lat:.4f}, {s.destino_lon:.4f}',
            'origen': [s.origen_lat, s.origen_lon], 'destino': [s.destino_lat, s.destino_lon],
            'medio': s.medio_transporte, 'riesgo': s.riesgo_calculado, 'tiempo': s.tiempo_estimado_min,
            'fecha': s.fecha_hora.strftime('%d-%m %H:%M')})
    return JsonResponse({'historial': lista})

def api_panico(request):
    if request.method != 'POST':
        return JsonResponse({'ok': False}, status=405)
    try:
        lat, lon = float(request.POST.get('lat')), float(request.POST.get('lon'))
    except (TypeError, ValueError):
        lat, lon = None, None
    BotonPanico.objects.create(latitud=lat, longitud=lon)
    return JsonResponse({
        'ok': True,
        'mensaje': 'Se registró la alerta en el sistema. Esta versión de prueba aún no envía mensajes '
                   'a los contactos: en una emergencia real llama al 133 (Carabineros) o al 131 (ambulancia).'})


def api_llegadas(request, codigo):
    micro = request.GET.get('micro', '').strip().upper()
    try:
        datos = _pedir_json(f"{settings.LLEGADAS_URL}/{urllib.parse.quote(codigo)}")
    except Exception:
        return JsonResponse({'ok': False, 'error': 'No se pudo consultar las llegadas en este momento.'})
    if datos.get('status_code', 0) != 0:
        return JsonResponse({'ok': False, 'error': datos.get('status_description') or 'Sin información del paradero.'})
    servicios = []
    for sv in datos.get('services', []):
        if micro and sv.get('id', '').upper() != micro:
            continue
        buses = [{'patente': b.get('id', ''), 'metros': b.get('meters_distance', 0),
                  'min': b.get('min_arrival_time', 0), 'max': b.get('max_arrival_time', 0)}
                 for b in (sv.get('buses') or [])]
        servicios.append({'micro': sv.get('id', ''), 'buses': buses, 'mensaje': sv.get('status_description', '')})
    servicios.sort(key=lambda x: (not x['buses'], x['buses'][0]['min'] if x['buses'] else 0))
    return JsonResponse({'ok': True, 'paradero': datos.get('name', ''), 'servicios': servicios})


def api_buses(request):
    micro = request.GET.get('micro', '').strip()
    if not micro:
        return JsonResponse({'ok': False, 'error': 'Falta el número de micro.', 'buses': []})
    try:
        datos = _pedir_json(f"{settings.BUSES_URL}?route_id={urllib.parse.quote(micro)}&limit=100")
        buses = [{'patente': b.get('bus_plate_number', ''), 'lat': float(b['bus_lat']), 'lon': float(b['bus_lon']),
                  'velocidad': b.get('bus_speed'), 'sentido': b.get('direction_id')}
                 for b in datos.get('results', []) if b.get('bus_lat') and b.get('bus_lon')]
    except Exception:
        return JsonResponse({'ok': False, 'error': 'No se pudo consultar la posición de los buses.', 'buses': []})
    return JsonResponse({'ok': True, 'buses': buses})


COMISARIAS = {'lista': None}


def pedir_comisarias_a_overpass():
    consulta = lugares.consulta_comisarias()
    for servidor in settings.OVERPASS_URLS:
        try:
            peticion = urllib.request.Request(
                servidor, data=urllib.parse.urlencode({'data': consulta}).encode(),
                headers={'User-Agent': settings.USER_AGENT})
            with urllib.request.urlopen(peticion, timeout=70) as respuesta:
                datos = json.loads(respuesta.read().decode('utf-8'))
            lista = [c for c in lugares.leer_comisarias(datos) if en_santiago(c['lat'], c['lon'])]
            if lista:
                return lista
        except Exception:
            continue
    return None


def archivo_comisarias():
    return os.path.join(settings.BASE_DIR, 'datos', 'comisarias.json')


def obtener_comisarias(forzar=False):
    ruta = archivo_comisarias()
    if not forzar:
        if COMISARIAS['lista'] is not None:
            return COMISARIAS['lista']
        if os.path.exists(ruta):
            with open(ruta, encoding='utf-8') as f:
                COMISARIAS['lista'] = json.load(f)
            return COMISARIAS['lista']
        return None
    lista = pedir_comisarias_a_overpass()
    if lista is None:
        return None
    with open(ruta, 'w', encoding='utf-8') as f:
        json.dump(lista, f, ensure_ascii=False, indent=1)
    COMISARIAS['lista'] = lista
    return lista


COMISARIAS['descargando'] = False


def _descargar_comisarias():
    try:
        obtener_comisarias(forzar=True)
    finally:
        COMISARIAS['descargando'] = False


def iniciar_descarga_comisarias():
    if COMISARIAS['descargando'] or COMISARIAS['lista'] is not None or os.path.exists(archivo_comisarias()):
        return
    COMISARIAS['descargando'] = True
    threading.Thread(target=_descargar_comisarias, daemon=True).start()


CACHE_OTROS = {}
RADIO_RUTA = 500


def _overpass(consulta):
    for servidor in settings.OVERPASS_URLS:
        try:
            peticion = urllib.request.Request(
                servidor, data=urllib.parse.urlencode({'data': consulta}).encode(),
                headers={'User-Agent': settings.USER_AGENT})
            with urllib.request.urlopen(peticion, timeout=25) as respuesta:
                return json.loads(respuesta.read().decode('utf-8'))
        except Exception:
            continue
    return None


def buscar_otros(clave, consulta, lat, lon):
    if clave in CACHE_OTROS:
        return CACHE_OTROS[clave]
    datos = _overpass(consulta)
    if datos is None:
        return None
    lista = lugares.leer_otros(datos, lat, lon)
    if len(CACHE_OTROS) > 200:
        CACHE_OTROS.clear()
    CACHE_OTROS[clave] = lista
    return lista


def leer_ruta(texto):
    puntos = []
    for par in texto.split(';')[:60]:
        lat, lon = par.split(',')
        puntos.append((float(lat), float(lon)))
    return puntos


LOCALES = {'lista': None}


def lugares_locales():
    if LOCALES['lista'] is None:
        ruta = os.path.join(settings.BASE_DIR, 'datos', 'lugares_seguros.json')
        if os.path.exists(ruta):
            with open(ruta, encoding='utf-8') as f:
                lista = json.load(f)
        else:
            zips = sorted(settings.GTFS_CARPETA.glob('GTFS_*.zip')) if os.path.isdir(settings.GTFS_CARPETA) else []
            lista = gtfs.lugares_seguros(zips[-1]) if zips else []
        LOCALES['lista'] = lista
    lista = list(LOCALES['lista'])
    comisarias = obtener_comisarias()
    if comisarias:
        lista += [c for c in comisarias
                  if not any(l['tipo'] == 'policia' and distancia_m_vista(c, l) < 150 for l in LOCALES['lista'])]
    return lista, comisarias


def distancia_m_vista(a, b):
    return riesgo.distancia_m(a['lat'], a['lon'], b['lat'], b['lon'])


def api_lugares_seguros(request):
    ruta = request.GET.get('ruta')
    try:
        if ruta:
            puntos = leer_ruta(ruta)
            if len(puntos) < 2:
                raise ValueError
        else:
            lat, lon = float(request.GET.get('lat')), float(request.GET.get('lon'))
            puntos = [(lat, lon), (lat, lon)]
        radio = min(max(int(request.GET.get('radio', RADIO_RUTA)), 100), 3000)
    except (TypeError, ValueError):
        return JsonResponse({'ok': False, 'error': 'Parámetros inválidos.', 'lugares': []}, status=400)

    if request.GET.get('fuente') == 'internet':
        comisarias = obtener_comisarias()
        if comisarias is None:
            iniciar_descarga_comisarias()
        clave = ('ruta', radio, tuple((round(a, 4), round(b, 4)) for a, b in puntos))
        otros = buscar_otros(clave, lugares.consulta_otros_ruta(puntos, radio), puntos[0][0], puntos[0][1])
        lista = lugares.cerca_de_ruta(otros or [], puntos, radio)
        return JsonResponse({'ok': otros is not None, 'lugares': lista, 'sin_comisarias': comisarias is None,
                             'descargando': COMISARIAS['descargando']})

    todos, comisarias = lugares_locales()
    if comisarias is None:
        iniciar_descarga_comisarias()
    cerca = lugares.cerca_de_ruta(todos, puntos, radio)
    lejos = False
    if not cerca:
        lejos = True
        cerca = sorted((dict(l, metros=round(lugares.distancia_a_ruta(l['lat'], l['lon'], puntos)))
                        for l in todos), key=lambda l: l['metros'])[:4]
    return JsonResponse({'ok': True, 'lugares': cerca[:40], 'lejos': lejos, 'radio': radio,
                         'sin_comisarias': comisarias is None, 'descargando': COMISARIAS['descargando']})
