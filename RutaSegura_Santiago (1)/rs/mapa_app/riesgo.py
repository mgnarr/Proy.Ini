import math
import unicodedata

PESO = {"Bajo": 1, "Medio": 2, "Alto": 3}
METROS_POR_GRADO_LAT = 111000
METROS_POR_GRADO_LON = 92800

def distancia_m(lat1, lon1, lat2, lon2):
    return math.hypot((lat1 - lat2) * METROS_POR_GRADO_LAT, (lon1 - lon2) * METROS_POR_GRADO_LON)

def clave_comuna(texto):
    texto = unicodedata.normalize("NFD", str(texto))
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = texto.upper().strip()
    if texto.startswith("COMUNA DE "):
        texto = texto[len("COMUNA DE "):]
    return " ".join(texto.split())

def nivel_desde_indice(indice):
    if indice < 34:
        return "Bajo"
    if indice < 67:
        return "Medio"
    return "Alto"

def zonas_desde_estadisticas(filas, centros, radio_cobertura=6000, radio_dibujo=2300):
    centros_por_clave = {clave_comuna(n): (n, c) for n, c in centros.items()}
    usar_tasa = len(filas) > 0 and all(f.get("poblacion") for f in filas)

    con_valor = []
    for f in filas:
        valor = f["delitos"] / f["poblacion"] * 100000 if usar_tasa else f["delitos"]
        con_valor.append((valor, f))
    con_valor.sort(key=lambda par: par[0])

    zonas = []
    sin_ubicacion = []
    ubicables = [par for par in con_valor if par[1]["comuna_clave"] in centros_por_clave]
    sin_ubicacion = [par[1]["comuna"] for par in con_valor if par[1]["comuna_clave"] not in centros_por_clave]

    total = len(ubicables)
    for posicion, (valor, f) in enumerate(ubicables):
        nivel = ("Bajo", "Medio", "Alto")[min(2, posicion * 3 // max(total, 1))]
        nombre, (lat, lon) = centros_por_clave[f["comuna_clave"]]
        zonas.append({
            "id": f["comuna_clave"],
            "sector": nombre,
            "comuna": nombre,
            "tipo_zona": "comunal",
            "lat": lat,
            "lon": lon,
            "radio_metros": radio_cobertura,
            "radio_dibujo": radio_dibujo,
            "nivel_riesgo": nivel,
            "delitos": f["delitos"],
            "valor": round(valor, 1),
            "metrica": "delitos cada 100.000 hab." if usar_tasa else "delitos totales",
            "periodo": f["periodo"],
            "fuente": f["fuente"],
            "ficticio": False,
        })
    return zonas, sin_ubicacion

def zonas_de_ejemplo(zonas_json):
    zonas = []
    for z in zonas_json:
        zonas.append({
            "id": z["id"],
            "sector": z["sector"],
            "comuna": z["comuna"],
            "tipo_zona": "ejemplo",
            "lat": z["lat"],
            "lon": z["lon"],
            "radio_metros": z["radio_metros"],
            "radio_dibujo": z["radio_metros"],
            "nivel_riesgo": z["nivel_riesgo"],
            "delitos": z["delitos_reportados"],
            "valor": z["delitos_reportados"],
            "metrica": "delitos simulados",
            "periodo": "DATO DE EJEMPLO",
            "fuente": "Datos simulados (no reales)",
            "ficticio": True,
            "calle_principal": z.get("calle_principal", ""),
            "iluminacion": z.get("iluminacion"),
            "punto_resguardo_cercano": z.get("punto_resguardo_cercano", ""),
        })
    return zonas

def zona_en_punto(lat, lon, zonas):
    mejor = None
    mejor_dist = None
    for z in zonas:
        d = distancia_m(lat, lon, z["lat"], z["lon"])
        if d <= z["radio_metros"] and (mejor is None or d < mejor_dist):
            mejor = z
            mejor_dist = d
    return mejor

def evaluar_ruta(coords, zonas):
    puntos = [(c[0], c[1]) for c in coords]
    suma_ponderada = 0.0
    metros_total = 0.0
    metros_alto = 0.0
    metros_por_zona = {}

    if len(puntos) == 1:
        puntos = puntos * 2

    for i in range(len(puntos) - 1):
        (lat1, lon1), (lat2, lon2) = puntos[i], puntos[i + 1]
        largo = distancia_m(lat1, lon1, lat2, lon2)
        if largo == 0:
            continue
        zona = zona_en_punto((lat1 + lat2) / 2, (lon1 + lon2) / 2, zonas)
        peso = PESO[zona["nivel_riesgo"]] if zona else 1
        suma_ponderada += peso * largo
        metros_total += largo
        if peso == 3:
            metros_alto += largo
        if zona:
            clave = zona["id"]
            if clave not in metros_por_zona:
                metros_por_zona[clave] = [zona, 0.0]
            metros_por_zona[clave][1] += largo

    if metros_total == 0:
        indice = 0
        pct_alto = 0
    else:
        promedio = suma_ponderada / metros_total
        indice = round((promedio - 1) / 2 * 100)
        pct_alto = round(metros_alto / metros_total * 100)

    ordenadas = sorted(metros_por_zona.values(), key=lambda par: -par[1])
    zonas_en_ruta = [{
        "sector": z["sector"],
        "nivel_riesgo": z["nivel_riesgo"],
        "tipo_zona": z["tipo_zona"],
        "metros": round(m),
        "detalle": f"{z['delitos']} ({z['metrica']}, {z['periodo']})",
    } for z, m in ordenadas]

    return {
        "indice_riesgo": indice,
        "nivel_riesgo": nivel_desde_indice(indice),
        "pct_zona_alta": pct_alto,
        "metros": round(metros_total),
        "zonas_en_ruta": zonas_en_ruta,
    }

def marcar_mas_segura(alternativas):
    if not alternativas:
        return
    mejor = min(alternativas, key=lambda a: (a["indice_riesgo"], a["tiempo_min"]))
    for a in alternativas:
        a["mas_segura"] = a is mejor
