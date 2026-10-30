import csv
import io
import json
import re
import zipfile
from collections import Counter

from .riesgo import distancia_m

def leer_csv(zf, nombre):
    with zf.open(nombre) as crudo:
        texto = io.TextIOWrapper(crudo, encoding="utf-8-sig", newline="")
        for fila in csv.DictReader(texto):
            yield {k.strip(): (v or "").strip() for k, v in fila.items() if k}

def hora_a_segundos(texto):
    try:
        h, m, s = texto.split(":")
        return int(h) * 3600 + int(m) * 60 + int(s)
    except ValueError:
        return None

def adelgazar(puntos, minimo_m=30):
    if not puntos:
        return []
    resultado = [puntos[0]]
    for p in puntos[1:-1]:
        if distancia_m(p[0], p[1], resultado[-1][0], resultado[-1][1]) >= minimo_m:
            resultado.append(p)
    if len(puntos) > 1:
        resultado.append(puntos[-1])
    return resultado

def leer_gtfs(ruta_zip, aviso=print):
    with zipfile.ZipFile(ruta_zip) as zf:
        nombres = set(zf.namelist())
        for requerido in ("routes.txt", "trips.txt", "stop_times.txt", "stops.txt"):
            if requerido not in nombres:
                raise ValueError(f"El archivo no trae {requerido}. ¿Es un GTFS válido?")

        rutas = {}
        for f in leer_csv(zf, "routes.txt"):
            if f.get("route_type", "3") not in ("3", ""):
                continue
            rutas[f["route_id"]] = {
                "route_id": f["route_id"],
                "numero": f.get("route_short_name") or f["route_id"],
                "nombre": f.get("route_long_name", ""),
                "color": f.get("route_color", ""),
            }
        aviso(f"routes.txt: {len(rutas)} recorridos")

        viajes = {}
        por_servicio = Counter()
        for f in leer_csv(zf, "trips.txt"):
            if f["route_id"] not in rutas:
                continue
            viajes[f["trip_id"]] = f
            por_servicio[f.get("service_id", "")] += 1
        servicio = por_servicio.most_common(1)[0][0] if por_servicio else ""
        viajes = {t: f for t, f in viajes.items() if f.get("service_id", "") == servicio}
        aviso(f"trips.txt: {len(viajes)} viajes del servicio de referencia '{servicio}'")

        cuenta = Counter()
        for f in leer_csv(zf, "stop_times.txt"):
            if f["trip_id"] in viajes:
                cuenta[f["trip_id"]] += 1

        salidas = Counter()
        if "frequencies.txt" in nombres:
            for f in leer_csv(zf, "frequencies.txt"):
                if f["trip_id"] not in viajes:
                    continue
                ini = hora_a_segundos(f.get("start_time", ""))
                fin = hora_a_segundos(f.get("end_time", ""))
                intervalo = int(f.get("headway_secs") or 0)
                if ini is not None and fin is not None and intervalo > 0 and fin > ini:
                    v = viajes[f["trip_id"]]
                    salidas[(v["route_id"], v.get("direction_id") or "0")] += (fin - ini) / intervalo

        elegidos = {}
        n_viajes = Counter()
        for trip_id, f in viajes.items():
            clave = (f["route_id"], f.get("direction_id") or "0")
            n_viajes[clave] += 1
            if clave not in elegidos or cuenta[trip_id] > cuenta[elegidos[clave]]:
                elegidos[clave] = trip_id
        trip_a_clave = {t: c for c, t in elegidos.items()}
        aviso(f"{len(elegidos)} sentidos de recorrido")

        filas_por_viaje = {t: [] for t in elegidos.values()}
        for f in leer_csv(zf, "stop_times.txt"):
            if f["trip_id"] in filas_por_viaje:
                filas_por_viaje[f["trip_id"]].append(f)

        paradas = {}
        for f in leer_csv(zf, "stops.txt"):
            try:
                paradas[f["stop_id"]] = {
                    "stop_id": f["stop_id"],
                    "nombre": f.get("stop_name", ""),
                    "lat": float(f["stop_lat"]),
                    "lon": float(f["stop_lon"]),
                }
            except (KeyError, ValueError):
                continue

        shapes_necesarios = {viajes[t].get("shape_id", "") for t in elegidos.values()}
        shapes_necesarios.discard("")
        puntos_shape = {s: [] for s in shapes_necesarios}
        if "shapes.txt" in nombres:
            for f in leer_csv(zf, "shapes.txt"):
                if f["shape_id"] in puntos_shape:
                    try:
                        puntos_shape[f["shape_id"]].append(
                            (int(float(f["shape_pt_sequence"])), float(f["shape_pt_lat"]), float(f["shape_pt_lon"])))
                    except ValueError:
                        continue
        else:
            aviso("AVISO: el GTFS no trae shapes.txt, no se podrán dibujar los recorridos.")

        version = ""
        if "feed_info.txt" in nombres:
            for f in leer_csv(zf, "feed_info.txt"):
                version = f.get("feed_version", "") or f.get("feed_start_date", "")
                break

    sentidos = []
    for clave, trip_id in elegidos.items():
        route_id, direction = clave
        viaje = viajes[trip_id]
        filas = sorted(filas_por_viaje[trip_id], key=lambda f: int(float(f["stop_sequence"])))
        t0 = None
        secuencia = []
        for f in filas:
            if f["stop_id"] not in paradas:
                continue
            seg = hora_a_segundos(f.get("arrival_time") or f.get("departure_time") or "")
            if t0 is None and seg is not None:
                t0 = seg
            secuencia.append({
                "stop_id": f["stop_id"],
                "segundos": (seg - t0) if (seg is not None and t0 is not None) else None,
            })
        puntos = sorted(puntos_shape.get(viaje.get("shape_id", ""), []))
        trazado = adelgazar([[lat, lon] for _, lat, lon in puntos])
        sentidos.append({
            "route_id": route_id,
            "direction_id": int(direction) if direction.isdigit() else 0,
            "destino": viaje.get("trip_headsign", ""),
            "trazado": trazado,
            "n_viajes": max(1, round(salidas[clave])) if salidas[clave] else n_viajes[clave],
            "secuencia": secuencia,
        })

    usadas = {s["stop_id"] for sen in sentidos for s in sen["secuencia"]}
    return {
        "rutas": [r for r in rutas.values() if any(s["route_id"] == r["route_id"] for s in sentidos)],
        "paradas": [p for sid, p in paradas.items() if sid in usadas],
        "sentidos": sentidos,
        "servicio_referencia": servicio,
        "version": version,
    }

def encontrar_url_vigente(html, base="https://dtpm.cl"):
    enlaces = re.findall(r'href="([^"]*GTFS_(\d{8})[^"]*\.zip)"', html, flags=re.IGNORECASE)
    if not enlaces:
        return None
    url, _ = max(enlaces, key=lambda par: par[1])
    if url.startswith("http"):
        return url
    return base + (url if url.startswith("/") else "/" + url)


PATRONES_LUGARES = [
    ('hospital', 'Hospital / centro de salud', r'hospital|cl[ií]nica|cesfam|cecosf|consultorio|\bposta\b|sapu|cosam'),
    ('policia', 'Comisaría / Carabineros', r'comisar|ret[eé]n|tenencia|carabineros|\bpdi\b|investigaciones'),
    ('mall', 'Centro comercial', r'\bmall\b|centro comercial|costanera center|portal la dehesa|paseo (quil[ií]n|los dominicos)|open plaza'),
    ('publico', 'Lugar público concurrido', r'^municipalidad|universidad|campus|inacap|duoc|^plaza de |^plaza italia|^terminal (de buses|san borja|las acacias|los libertadores)'),
    ('super', 'Supermercado', r'l[ií]der|jumbo|unimarc|santa isabel|tottus|supermercado|acuenta'),
]


def lugares_seguros(ruta_zip):
    lugares = []
    with zipfile.ZipFile(ruta_zip) as zf:
        for f in leer_csv(zf, "stops.txt"):
            try:
                lat, lon = float(f["stop_lat"]), float(f["stop_lon"])
            except (KeyError, ValueError):
                continue
            tipo_ubicacion = f.get("location_type", "")
            nombre = re.sub(r"^[A-Za-z]{1,3}\d+[A-Za-z]?-", "", f.get("stop_name", "")).strip()
            if tipo_ubicacion == "1":
                lugares.append(("metro", "Estación de Metro", "Metro " + nombre, lat, lon))
                continue
            if tipo_ubicacion in ("2", "3", "4") or not nombre or re.search(r"esq\.", nombre, re.I):
                continue
            lugar = re.sub(r"^Parada\s*\d*\s*/\s*", "", nombre)
            if lugar.startswith("(M)") or "Dirección" in lugar or "Direccion" in lugar:
                continue
            lugar = lugar.split(" - ")[0].strip()
            for tipo, categoria, patron in PATRONES_LUGARES:
                if re.search(patron, lugar, re.I):
                    lugares.append((tipo, categoria, lugar, lat, lon))
                    break
    resultado = []
    for tipo, categoria, nombre, lat, lon in lugares:
        if any(r["tipo"] == tipo and r["nombre"].lower() == nombre.lower()
               and distancia_m(lat, lon, r["lat"], r["lon"]) < 700 for r in resultado):
            continue
        resultado.append({"tipo": tipo, "categoria": categoria, "nombre": nombre,
                          "lat": round(lat, 6), "lon": round(lon, 6)})
    return resultado
