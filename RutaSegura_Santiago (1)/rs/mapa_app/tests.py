import io
import json
import tempfile
import zipfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase

from . import gtfs, lugares, riesgo, transporte

def crear_gtfs_de_prueba(ruta):
    archivos = {
        "routes.txt": "route_id,route_short_name,route_long_name,route_color\n"
                      "R100,100,Prueba uno,FF0000\nR200,200,Prueba dos,0000FF\n",
        "trips.txt": "route_id,service_id,trip_id,direction_id,shape_id,trip_headsign\n"
                     "R100,L,T100a,0,S100,Hacia C\nR100,L,T100b,0,S100,Hacia C\n"
                     "R200,L,T200a,0,S200,Hacia E\nR200,D,T200d,0,S200,Hacia E\n",
        "stops.txt": "stop_id,stop_name,stop_lat,stop_lon\n"
                     "A,Parada A,-33.4500,-70.6600\nB,Parada B,-33.4500,-70.6500\n"
                     "C,Parada C,-33.4500,-70.6400\nD,Parada D,-33.4500,-70.6300\n"
                     "E,Parada E,-33.4500,-70.6200\n",
        "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n"
                          "T100a,08:00:00,08:00:00,A,1\nT100a,08:05:00,08:05:00,B,2\nT100a,08:10:00,08:10:00,C,3\n"
                          "T100b,09:00:00,09:00:00,A,1\nT100b,09:10:00,09:10:00,C,2\n"
                          "T200a,08:00:00,08:00:00,C,1\nT200a,08:06:00,08:06:00,D,2\nT200a,08:12:00,08:12:00,E,3\n"
                          "T200d,08:00:00,08:00:00,C,1\nT200d,08:12:00,08:12:00,E,2\n",
        "shapes.txt": "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\n"
                      "S100,-33.4500,-70.6600,1\nS100,-33.4500,-70.6400,2\n"
                      "S200,-33.4500,-70.6400,1\nS200,-33.4500,-70.6200,2\n",
    }
    with zipfile.ZipFile(ruta, "w") as zf:
        for nombre, texto in archivos.items():
            zf.writestr(nombre, texto)

def preparar_datos_transporte(datos):
    paradas = {p["stop_id"]: p for p in datos["paradas"]}
    rutas = {r["route_id"]: r for r in datos["rutas"]}
    lista_paradas = [{"id": p["stop_id"], "nombre": p["nombre"], "lat": p["lat"], "lon": p["lon"]}
                     for p in datos["paradas"]]
    secuencias, sentidos = {}, {}
    for n, s in enumerate(datos["sentidos"]):
        secuencias[n] = [{"parada_id": x["stop_id"], "nombre": paradas[x["stop_id"]]["nombre"],
                          "lat": paradas[x["stop_id"]]["lat"], "lon": paradas[x["stop_id"]]["lon"],
                          "segundos": x["segundos"]} for x in s["secuencia"]]
        sentidos[n] = {"sentido_id": n, "numero": rutas[s["route_id"]]["numero"], "destino": s["destino"],
                       "color": rutas[s["route_id"]]["color"], "n_viajes": s["n_viajes"]}
    return lista_paradas, secuencias, sentidos

class GtfsTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        self.zip = Path(self.carpeta.name) / "prueba.zip"
        crear_gtfs_de_prueba(self.zip)

    def tearDown(self):
        self.carpeta.cleanup()

    def test_lee_recorridos_y_secuencias(self):
        datos = gtfs.leer_gtfs(self.zip, aviso=lambda *a: None)
        self.assertEqual(datos["servicio_referencia"], "L")
        self.assertEqual(len(datos["sentidos"]), 2)
        s100 = [s for s in datos["sentidos"] if s["route_id"] == "R100"][0]
        self.assertEqual(s100["n_viajes"], 2)
        self.assertEqual([x["stop_id"] for x in s100["secuencia"]], ["A", "B", "C"])
        self.assertEqual(s100["secuencia"][2]["segundos"], 600)
        self.assertEqual(len(s100["trazado"]), 2)

    def test_hora_sobre_24(self):
        self.assertEqual(gtfs.hora_a_segundos("25:10:00"), 25 * 3600 + 600)

    def test_encuentra_url_vigente(self):
        html = '<a href="/descargas/gtfs/GTFS_20260901.zip">x</a><a href="/descargas/gtfs/GTFS_20261003.zip">y</a>'
        self.assertEqual(gtfs.encontrar_url_vigente(html), "https://dtpm.cl/descargas/gtfs/GTFS_20261003.zip")

class TransporteTests(SimpleTestCase):
    def setUp(self):
        self.carpeta = tempfile.TemporaryDirectory()
        zip_ = Path(self.carpeta.name) / "prueba.zip"
        crear_gtfs_de_prueba(zip_)
        self.paradas, self.sec, self.sent = preparar_datos_transporte(
            gtfs.leer_gtfs(zip_, aviso=lambda *a: None))

    def tearDown(self):
        self.carpeta.cleanup()

    def test_viaje_directo(self):
        alts = transporte.buscar_alternativas((-33.4501, -70.6601), (-33.4501, -70.6401),
                                              self.paradas, self.sec, self.sent)
        directos = [a for a in alts if a["trasbordos"] == 0]
        self.assertEqual([a["tramos"][0]["micro"] for a in directos], ["100"])
        self.assertEqual(directos[0]["tramos"][0]["minutos_viaje"], 10)

    def test_un_trasbordo(self):
        alts = transporte.buscar_alternativas((-33.4501, -70.6601), (-33.4501, -70.6201),
                                              self.paradas, self.sec, self.sent)
        self.assertEqual(len(alts), 1)
        self.assertEqual(alts[0]["trasbordos"], 1)
        self.assertEqual([t["micro"] for t in alts[0]["tramos"]], ["100", "200"])

    def test_sin_paraderos_cerca(self):
        alts = transporte.buscar_alternativas((-33.30, -70.80), (-33.31, -70.81),
                                              self.paradas, self.sec, self.sent)
        self.assertEqual(alts, [])

class RiesgoTests(SimpleTestCase):
    def test_clave_comuna(self):
        self.assertEqual(riesgo.clave_comuna("Ñuñoa"), "NUNOA")
        self.assertEqual(riesgo.clave_comuna("  comuna de  San Miguel "), "SAN MIGUEL")

    def test_niveles_por_terciles(self):
        filas = [{"comuna": c, "comuna_clave": riesgo.clave_comuna(c), "delitos": d, "poblacion": None,
                  "periodo": "prueba", "fuente": "prueba"}
                 for c, d in [("Santiago", 900), ("Providencia", 100), ("Maipú", 500),
                              ("Las Condes", 50), ("Renca", 700), ("Ñuñoa", 300)]]
        centros = {"Santiago": (-33.45, -70.65), "Providencia": (-33.43, -70.61), "Maipú": (-33.51, -70.76),
                   "Las Condes": (-33.41, -70.57), "Renca": (-33.40, -70.72), "Ñuñoa": (-33.45, -70.60)}
        zonas, sin = riesgo.zonas_desde_estadisticas(filas, centros)
        niveles = {z["sector"]: z["nivel_riesgo"] for z in zonas}
        self.assertEqual(sin, [])
        self.assertEqual(niveles["Las Condes"], "Bajo")
        self.assertEqual(niveles["Santiago"], "Alto")

    def test_indice_de_ruta(self):
        zona = {"id": 1, "sector": "Z", "nivel_riesgo": "Alto", "tipo_zona": "ejemplo", "lat": -33.45,
                "lon": -70.65, "radio_metros": 1000, "delitos": 10, "metrica": "m", "periodo": "p"}
        dentro = riesgo.evaluar_ruta([[-33.4500, -70.6500], [-33.4500, -70.6490]], [zona])
        fuera = riesgo.evaluar_ruta([[-33.40, -70.60], [-33.40, -70.59]], [zona])
        self.assertEqual(dentro["indice_riesgo"], 100)
        self.assertEqual(fuera["indice_riesgo"], 0)

class PaginasTests(TestCase):
    def test_pagina_principal(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)

    def test_api_zonas_y_fuentes(self):
        self.assertEqual(self.client.get("/api/zonas/").status_code, 200)
        self.assertEqual(self.client.get("/api/fuentes/?sin_importar=1").status_code, 200)

    def test_zonas_de_ejemplo_marcadas_como_simuladas(self):
        datos = json.loads(self.client.get("/api/zonas/").content)
        self.assertEqual(datos["modo"], "ejemplo")
        self.assertTrue(all(z["ficticio"] for z in datos["zonas"]))

    def test_transporte_sin_datos_gtfs(self):
        r = self.client.get("/api/transporte/?lat1=-33.45&lon1=-70.65&lat2=-33.44&lon2=-70.60")
        datos = json.loads(r.content)
        self.assertFalse(datos["gtfs_disponible"])

    def test_parametros_invalidos(self):
        self.assertEqual(self.client.get("/api/calcular_ruta/?lat1=abc").status_code, 400)


class LugaresTests(SimpleTestCase):
    def setUp(self):
        self.calles = lugares.Calles([
            ("PG291-Vicuña Mackenna / esq. San Miguel", -33.50, -70.61),
            ("PE1488-Av. Vicuña Mackenna / esq. Millaray", -33.52, -70.60),
            ("PC200-Parada 3 / Parque Balmaceda", -33.43, -70.62),
            ("PJ432-Mapocho Norte / esq. Diagonal Reny", -33.41, -70.66),
        ])

    def test_busca_calle_con_error_de_escritura(self):
        nombres = [r["nombre"] for r in self.calles.buscar("vicuña makena")]
        self.assertTrue(all("Mackenna" in n for n in nombres))
        self.assertEqual(len(nombres), 2)

    def test_busca_esquina(self):
        self.assertEqual(self.calles.buscar("mackenna con millaray")[0]["nombre"], "Av. Vicuña Mackenna con Millaray")

    def test_quita_parada_del_nombre(self):
        self.assertEqual(self.calles.buscar("balmaceda")[0]["nombre"], "Parque Balmaceda")

    def test_comunas(self):
        comunas = lugares.Comunas(Path(__file__).resolve().parent.parent / "datos" / "comunas_santiago.geojson")
        self.assertIsNone(comunas.comuna_de(-33.03, -71.55))
        self.assertTrue(comunas.en_santiago(-33.4372, -70.6506))

    def test_lee_comisarias(self):
        respuesta = {"elements": [
            {"type": "node", "lat": -33.45, "lon": -70.65, "tags": {"amenity": "police", "name": "1ª Comisaría Santiago"}},
            {"type": "way", "center": {"lat": -33.4501, "lon": -70.6501}, "tags": {"amenity": "police", "name": "1ª Comisaría Santiago"}},
            {"type": "way", "center": {"lat": -33.50, "lon": -70.70}, "tags": {"amenity": "police", "name": "Prefectura PDI", "operator": "Policía de Investigaciones"}},
            {"type": "relation", "tags": {"amenity": "police"}},
        ]}
        lista = lugares.leer_comisarias(respuesta)
        self.assertEqual(len(lista), 2)
        self.assertEqual(lista[1]["categoria"], "PDI")
        cerca = lugares.mas_cercanas(lista, -33.451, -70.651, cantidad=1)
        self.assertEqual(cerca[0]["nombre"], "1ª Comisaría Santiago")
        self.assertIn("amenity", lugares.consulta_comisarias())

    def test_lee_otros_lugares(self):
        respuesta = {"elements": [
            {"type": "node", "lat": -33.45, "lon": -70.65, "tags": {"amenity": "hospital", "name": "Hospital Prueba"}},
            {"type": "way", "center": {"lat": -33.451, "lon": -70.651}, "tags": {"shop": "mall"}},
            {"type": "node", "lat": -33.4, "lon": -70.6, "tags": {"amenity": "bench"}},
        ]}
        lista = lugares.leer_otros(respuesta, -33.45, -70.65)
        self.assertEqual([l["tipo"] for l in lista], ["hospital", "mall"])
        self.assertEqual(lista[0]["metros"], 0)

    def test_lugares_cerca_de_la_ruta(self):
        ruta = [(-33.4500, -70.6500), (-33.4500, -70.6400)]
        lista = [
            {"tipo": "policia", "categoria": "c", "nombre": "Cerca", "lat": -33.4510, "lon": -70.6450},
            {"tipo": "policia", "categoria": "c", "nombre": "Lejos", "lat": -33.4700, "lon": -70.6450},
        ]
        cerca = lugares.cerca_de_ruta(lista, ruta, 400)
        self.assertEqual([l["nombre"] for l in cerca], ["Cerca"])
        self.assertIn("around:400", lugares.consulta_otros_ruta(ruta, 400))

    def test_lugares_seguros_desde_gtfs(self):
        carpeta = tempfile.TemporaryDirectory()
        ruta = Path(carpeta.name) / "lugares.zip"
        stops = ("stop_id,stop_name,stop_lat,stop_lon,location_type\n"
                 "PA1,PA1-Parada / 26ª Comisaría,-33.45,-70.65,\n"
                 "PA2,PA2-Parada 2 / Hospital Barros Luco,-33.50,-70.66,\n"
                 "PA3,PA3-Bilbao / esq. Hospital,-33.40,-70.60,\n"
                 "PA4,PA4-Parada / Mall Plaza Norte - Santa Elena,-33.37,-70.68,\n"
                 "BA,Baquedano,-33.437,-70.634,1\n")
        with zipfile.ZipFile(ruta, "w") as zf:
            zf.writestr("stops.txt", stops)
        lista = gtfs.lugares_seguros(ruta)
        carpeta.cleanup()
        self.assertEqual(sorted(l["tipo"] for l in lista), ["hospital", "mall", "metro", "policia"])
        self.assertIn("Metro Baquedano", [l["nombre"] for l in lista])

