from .riesgo import distancia_m

RADIO_CAMINATA = 500
RADIO_TRASBORDO = 250
M_POR_MIN_CAMINANDO = 80
M_POR_MIN_MICRO = 250
HORAS_DE_SERVICIO = 18

def espera_estimada(n_viajes):
    if not n_viajes:
        return 5, False
    intervalo = HORAS_DE_SERVICIO * 60 / n_viajes
    return round(min(intervalo / 2, 20), 1), True

def minutos_de_viaje(seq, i, j):
    a, b = seq[i]["segundos"], seq[j]["segundos"]
    if a is not None and b is not None and b >= a:
        return max(1, round((b - a) / 60)), False
    largo = sum(distancia_m(seq[k]["lat"], seq[k]["lon"], seq[k + 1]["lat"], seq[k + 1]["lon"])
                for k in range(i, j))
    return max(1, round(largo / M_POR_MIN_MICRO)), True

def _punto(parada):
    return {"nombre": parada["nombre"], "lat": parada["lat"], "lon": parada["lon"], "codigo": parada.get("codigo", "")}

def _tramo(info, seq, i, j):
    minutos, estimado = minutos_de_viaje(seq, i, j)
    espera, espera_gtfs = espera_estimada(info.get("n_viajes"))
    return {
        "micro": info["numero"],
        "destino": info.get("destino", ""),
        "color": info.get("color", ""),
        "sentido_id": info["sentido_id"],
        "sube": _punto(seq[i]),
        "baja": _punto(seq[j]),
        "n_paradas": j - i,
        "paradas": [_punto(p) for p in seq[i:j + 1]],
        "minutos_viaje": minutos,
        "viaje_estimado": estimado,
        "minutos_espera": espera,
        "espera_calculada_con_gtfs": espera_gtfs,
    }

def _cerca(paradas, lat, lon, radio):
    resultado = {}
    for p in paradas:
        d = distancia_m(lat, lon, p["lat"], p["lon"])
        if d <= radio:
            resultado[p["id"]] = d
    return resultado

def buscar_alternativas(origen, destino, paradas, secuencias, sentidos, maximo=5):
    cerca_o = _cerca(paradas, origen[0], origen[1], RADIO_CAMINATA)
    cerca_d = _cerca(paradas, destino[0], destino[1], RADIO_CAMINATA)
    if not cerca_o or not cerca_d:
        return []

    directos = {}
    subidas = []
    for sid, seq in secuencias.items():
        indices_o = [(k, cerca_o[p["parada_id"]]) for k, p in enumerate(seq) if p["parada_id"] in cerca_o]
        indices_d = [(k, cerca_d[p["parada_id"]]) for k, p in enumerate(seq) if p["parada_id"] in cerca_d]
        if indices_o:
            i, d_o = min(indices_o, key=lambda par: par[1])
            subidas.append((sid, i, d_o))
        mejor = None
        for i, d_o in indices_o:
            for j, d_d in indices_d:
                if j > i and (mejor is None or d_o + d_d < mejor[2] + mejor[3]):
                    mejor = (i, j, d_o, d_d)
        if mejor:
            i, j, d_o, d_d = mejor
            tramo = _tramo(sentidos[sid], seq, i, j)
            caminata = d_o + d_d
            tiempo = round(caminata / M_POR_MIN_CAMINANDO + tramo["minutos_espera"] + tramo["minutos_viaje"])
            alt = {"tipo": "directo", "trasbordos": 0, "tramos": [tramo], "caminata_m": round(caminata),
                   "caminata_inicio": round(d_o), "caminata_final": round(d_d),
                   "caminata_trasbordo": 0, "tiempo_min": max(1, tiempo)}
            numero = tramo["micro"]
            if numero not in directos or alt["tiempo_min"] < directos[numero]["tiempo_min"]:
                directos[numero] = alt

    celdas = {}
    for sid, seq in secuencias.items():
        indices_d = [(j, cerca_d[p["parada_id"]]) for j, p in enumerate(seq) if p["parada_id"] in cerca_d]
        if not indices_d:
            continue
        j, d_d = min(indices_d, key=lambda par: par[1])
        for k in range(j):
            p = seq[k]
            celda = (round(p["lat"] / 0.003), round(p["lon"] / 0.003))
            celdas.setdefault(celda, []).append((sid, k, j, d_d))

    con_trasbordo = {}
    for sid1, i, d_o in subidas:
        seq1 = secuencias[sid1]
        info1 = sentidos[sid1]
        for k in range(i + 1, len(seq1)):
            p1 = seq1[k]
            ci, cj = round(p1["lat"] / 0.003), round(p1["lon"] / 0.003)
            for di in (-1, 0, 1):
                for dj in (-1, 0, 1):
                    for sid2, m, j, d_d in celdas.get((ci + di, cj + dj), []):
                        info2 = sentidos[sid2]
                        if info2["numero"] == info1["numero"]:
                            continue
                        p2 = secuencias[sid2][m]
                        caminar = distancia_m(p1["lat"], p1["lon"], p2["lat"], p2["lon"])
                        if caminar > RADIO_TRASBORDO:
                            continue
                        t1 = _tramo(info1, seq1, i, k)
                        t2 = _tramo(info2, secuencias[sid2], m, j)
                        caminata = d_o + caminar + d_d
                        tiempo = round(caminata / M_POR_MIN_CAMINANDO + t1["minutos_espera"] + t1["minutos_viaje"]
                                       + t2["minutos_espera"] + t2["minutos_viaje"])
                        alt = {"tipo": "trasbordo", "trasbordos": 1, "tramos": [t1, t2],
                               "caminata_m": round(caminata), "caminata_inicio": round(d_o),
                               "caminata_final": round(d_d), "caminata_trasbordo": round(caminar),
                               "tiempo_min": max(1, tiempo)}
                        clave = (info1["numero"], info2["numero"])
                        if clave not in con_trasbordo or alt["tiempo_min"] < con_trasbordo[clave]["tiempo_min"]:
                            con_trasbordo[clave] = alt

    lista_directos = sorted(directos.values(), key=lambda a: a["tiempo_min"])[:maximo]
    lista_trasbordo = sorted(con_trasbordo.values(), key=lambda a: a["tiempo_min"])[:3]
    return lista_directos + lista_trasbordo

def puntos_de_alternativa(origen, destino, alt):
    puntos = [[origen[0], origen[1]]]
    for tramo in alt["tramos"]:
        puntos += [[p["lat"], p["lon"]] for p in tramo["paradas"]]
    puntos.append([destino[0], destino[1]])
    return puntos

def recortar_trazado(trazado, sube, baja):
    if len(trazado) < 2:
        return []

    def indice_mas_cercano(punto):
        mejor, mejor_d = 0, None
        for k, p in enumerate(trazado):
            d = distancia_m(p[0], p[1], punto["lat"], punto["lon"])
            if mejor_d is None or d < mejor_d:
                mejor, mejor_d = k, d
        return mejor

    i, j = indice_mas_cercano(sube), indice_mas_cercano(baja)
    if i >= j:
        return []
    return trazado[i:j + 1]

def largo_m(puntos):
    return round(sum(distancia_m(puntos[k][0], puntos[k][1], puntos[k + 1][0], puntos[k + 1][1])
                     for k in range(len(puntos) - 1)))
