const CENTRO_SANTIAGO = [-33.4520, -70.6500];
const LIMITES = L.latLngBounds(L.latLng(-33.70, -70.90), L.latLng(-33.28, -70.42));
const COLOR_NIVEL = { Bajo: '#2e7d32', Medio: '#d98e04', Alto: '#c62828' };
const PESO_NIVEL = { Bajo: 0.35, Medio: 0.65, Alto: 1.0 };

const mapa = L.map('mapa', {
    center: CENTRO_SANTIAGO, zoom: 12, minZoom: 10, maxZoom: 18,
    maxBounds: LIMITES, maxBoundsViscosity: 0.8,
});

const ATRIB_OSM = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const ATRIB_ESRI = 'Tiles &copy; Esri';
const fondoEsri = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 19, attribution: ATRIB_ESRI });
const fondoGris = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}',
    { maxZoom: 16, maxNativeZoom: 16, attribution: ATRIB_ESRI });
const fondoOsm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    { maxZoom: 19, attribution: ATRIB_OSM });
let erroresFondo = 0;
fondoEsri.on('tileerror', function () {
    erroresFondo += 1;
    if (erroresFondo >= 4 && mapa.hasLayer(fondoEsri)) {
        mapa.removeLayer(fondoEsri);
        fondoOsm.addTo(mapa);
    }
});
fondoEsri.addTo(mapa);
L.control.layers({ 'Calles (Esri)': fondoEsri, 'OpenStreetMap': fondoOsm, 'Gris claro': fondoGris },
    null, { position: 'topright' }).addTo(mapa);

const capaZonas = L.layerGroup().addTo(mapa);
let capaCalor = null;
const capaMicros = L.layerGroup().addTo(mapa);
const capaParaderos = L.layerGroup();
const capaRuta = L.layerGroup().addTo(mapa);
const capaPuntos = L.layerGroup().addTo(mapa);

let origen = null;
let destino = null;
let medio = 'peaton';
let opciones = [];
let indiceActivo = 0;
let zonas = [];
const microsEnMapa = {};

function horas(min) {
    min = Math.round(min);
    if (min < 60) { return min + ' min'; }
    const h = Math.floor(min / 60), m = min % 60;
    return h + ' h' + (m ? ' ' + m + ' min' : '');
}

function el(id) { return document.getElementById(id); }

function esc(texto) {
    const div = document.createElement('div');
    div.textContent = texto == null ? '' : String(texto);
    return div.innerHTML;
}

function textoLlegada(b) {
    if (b.max <= 0) { return 'llegando'; }
    return (b.min === b.max ? b.min : b.min + ' a ' + b.max) + ' min (' + b.metros + ' m)';
}

async function cargarLlegadas(codigo, micro, destino) {
    destino.innerHTML = 'Consultando llegadas...';
    try {
        const d = await pedirJSON('/api/llegadas/' + encodeURIComponent(codigo) + '/' + (micro ? '?micro=' + encodeURIComponent(micro) : ''));
        if (!d.ok) { destino.innerHTML = '<em>' + esc(d.error) + '</em>'; return; }
        if (d.servicios.length === 0) { destino.innerHTML = '<em>Sin información de llegadas.</em>'; return; }
        let html = '<strong>Próximas llegadas (en vivo)</strong><ul class="llegadas">';
        d.servicios.slice(0, 8).forEach(function (sv) {
            if (sv.buses.length === 0) {
                html += '<li><b>' + esc(sv.micro) + '</b>: ' + esc(sv.mensaje || 'sin buses cerca') + '</li>';
            } else {
                html += '<li><b>' + esc(sv.micro) + '</b>: ' + sv.buses.slice(0, 2).map(textoLlegada).join(' · ') + '</li>';
            }
        });
        destino.innerHTML = html + '</ul>';
    } catch (error) {
        destino.innerHTML = '<em>No se pudo consultar las llegadas.</em>';
    }
}

const capaBuses = L.layerGroup().addTo(mapa);
async function mostrarBuses(micro, aviso) {
    capaBuses.clearLayers();
    aviso.textContent = 'Buscando buses...';
    try {
        const d = await pedirJSON('/api/buses/?micro=' + encodeURIComponent(micro));
        if (!d.ok) { aviso.textContent = d.error; return; }
        if (d.buses.length === 0) { aviso.textContent = 'No hay buses de la micro ' + micro + ' en circulación ahora.'; return; }
        d.buses.forEach(function (b) {
            L.circleMarker([b.lat, b.lon], { radius: 6, color: '#fff', weight: 2, fillColor: '#0f2d52', fillOpacity: 1 })
                .bindTooltip('Micro ' + micro + ' · ' + b.patente).addTo(capaBuses);
        });
        aviso.textContent = d.buses.length + ' buses de la micro ' + micro + ' en el mapa.';
    } catch (error) {
        aviso.textContent = 'No se pudo consultar la posición de los buses.';
    }
}

async function pedirJSON(url, opcionesFetch) {
    const respuesta = await fetch(url, opcionesFetch);
    return respuesta.json();
}

document.querySelectorAll('.tab').forEach(function (boton) {
    boton.addEventListener('click', function () {
        document.querySelectorAll('.tab').forEach(function (b) { b.classList.toggle('activa', b === boton); });
        ['ruta', 'capas', 'panico'].forEach(function (nombre) {
            el('tab-' + nombre).hidden = (nombre !== boton.dataset.tab);
        });
    });
});

async function cargarZonas() {
    const datos = await pedirJSON('/api/zonas/');
    zonas = datos.zonas;
    const aviso = el('aviso-datos');
    if (datos.modo === 'ejemplo') {
        aviso.className = 'aviso ejemplo';
        aviso.innerHTML = '<strong>Datos de ejemplo (simulados).</strong> Todavía no se importaron estadísticas reales; ' +
            'las zonas del mapa son ficticias. Ver la pestaña "Mapa de calor" para importarlas.';
    } else {
        const f = datos.fuente || {};
        aviso.className = 'aviso real';
        aviso.innerHTML = 'Riesgo <strong>por comuna</strong> según ' + esc(f.nombre) + ', período ' + esc(f.periodo) +
            ' (actualizado ' + esc(f.actualizado) + '). No muestra la ubicación exacta de los delitos.';
    }
    dibujarZonas();
}

function nivelesActivos() {
    return Array.from(document.querySelectorAll('.chk-nivel:checked')).map(function (c) { return c.value; });
}

function dibujarZonas() {
    capaZonas.clearLayers();
    if (capaCalor) { mapa.removeLayer(capaCalor); capaCalor = null; }
    const activos = nivelesActivos();
    const puntosCalor = [];

    zonas.forEach(function (z) {
        if (activos.indexOf(z.nivel_riesgo) === -1) { return; }
        puntosCalor.push([z.lat, z.lon, PESO_NIVEL[z.nivel_riesgo]]);

        const color = COLOR_NIVEL[z.nivel_riesgo];
        const circulo = L.circle([z.lat, z.lon], {
            radius: z.radio_dibujo, color: color, fillColor: color, fillOpacity: 0.16, weight: 1.5,
        }).addTo(capaZonas);

        let html = '<strong>' + esc(z.sector) + '</strong><br>Nivel de riesgo: <strong>' + esc(z.nivel_riesgo) + '</strong><br>' +
            esc(z.delitos) + ' (' + esc(z.metrica) + ')<br>Período: ' + esc(z.periodo) + '<br>Fuente: ' + esc(z.fuente);
        if (z.ficticio) { html += '<br><em>Dato simulado, no es real.</em>'; }
        if (z.tipo_zona === 'comunal') { html += '<br><em>Nivel comunal: no indica la ubicación exacta de los delitos.</em>'; }
        circulo.bindPopup(html);
    });

    capaCalor = L.heatLayer(puntosCalor, {
        radius: 38, blur: 28, maxZoom: 13, minOpacity: 0.35,
        gradient: { 0.3: '#2e7d32', 0.6: '#f2b705', 1.0: '#c62828' },
    });
    if (el('chk-calor').checked) { capaCalor.addTo(mapa); }
}

function conectarCapa(idCheck, capa) {
    el(idCheck).addEventListener('change', function () {
        if (el(idCheck).checked) { mapa.addLayer(capa); } else { mapa.removeLayer(capa); }
        if (idCheck === 'chk-paraderos') { cargarParaderos(); }
    });
}
conectarCapa('chk-micros', capaMicros);
conectarCapa('chk-paraderos', capaParaderos);
el('chk-zonas').addEventListener('change', function () {
    if (el('chk-zonas').checked) { mapa.addLayer(capaZonas); } else { mapa.removeLayer(capaZonas); }
});
el('chk-calor').addEventListener('change', function () {
    if (!capaCalor) { return; }
    if (el('chk-calor').checked) { capaCalor.addTo(mapa); } else { mapa.removeLayer(capaCalor); }
});
document.querySelectorAll('.chk-nivel').forEach(function (c) { c.addEventListener('change', dibujarZonas); });

const leyenda = L.control({ position: 'bottomright' });
leyenda.onAdd = function () {
    const div = L.DomUtil.create('div', 'leyenda');
    div.innerHTML =
        '<h4>Nivel de riesgo (zonas)</h4>' +
        '<i style="background:#2e7d32"></i>Bajo<br><i style="background:#d98e04"></i>Medio<br><i style="background:#c62828"></i>Alto<br>' +
        '<h4 style="margin-top:6px">Rutas</h4>' +
        '<i class="punteada"></i>Ruta a pie<br><i class="linea" style="border-color:#2563a8"></i>Ruta en auto<br>' +
        '<i class="linea" style="border-color:#7b3fa0"></i>Micro (GTFS)<br><i class="punteada" style="border-color:#7b3fa0"></i>Caminata a/desde paradero' +
        '<h4 style="margin-top:6px">Lugares seguros</h4>' +
        '<div class="item-seguro" data-tip="Lugares seguros cerca de tu ruta: comisarías, hospitales, bomberos, centros comerciales, supermercados, Metro y farmacias. Aparecen al buscar una ruta."><svg viewBox="0 0 24 28" width="20" height="23"><path d="M12 1 2 5v8c0 6.5 4.2 11.3 10 14 5.8-2.7 10-7.5 10-14V5z" fill="#1b9e3e" stroke="#fff" stroke-width="2"/><path d="M7.5 14l3.2 3.4L16.8 10" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg> Zona segura</div>';
    return div;
};
leyenda.addTo(mapa);

const controlCentrar = L.control({ position: 'topleft' });
controlCentrar.onAdd = function () {
    const boton = L.DomUtil.create('button', 'btn-centrar');
    boton.type = 'button';
    boton.textContent = 'Centrar en Santiago';
    L.DomEvent.disableClickPropagation(boton);
    boton.addEventListener('click', function () { mapa.setView(CENTRO_SANTIAGO, 12); });
    return boton;
};
controlCentrar.addTo(mapa);

function iconoPunto(color) {
    return L.divIcon({
        className: '',
        html: '<div style="width:16px;height:16px;border-radius:50%;background:' + color + ';border:3px solid #fff;box-shadow:0 0 4px rgba(0,0,0,.5)"></div>',
        iconSize: [16, 16], iconAnchor: [8, 8],
    });
}

function dibujarPuntos() {
    capaPuntos.clearLayers();
    if (origen) { L.marker([origen.lat, origen.lon], { icon: iconoPunto('#2e7d32') }).addTo(capaPuntos).bindTooltip('Origen'); }
    if (destino) { L.marker([destino.lat, destino.lon], { icon: iconoPunto('#c62828') }).addTo(capaPuntos).bindTooltip('Destino'); }
}

function crearBuscador(idInput, idLista, alElegir) {
    const input = el(idInput);
    const lista = el(idLista);
    let temporizador = null;

    function cerrar() { lista.hidden = true; lista.innerHTML = ''; }

    input.addEventListener('input', function () {
        alElegir(null);
        clearTimeout(temporizador);
        const texto = input.value.trim();
        if (texto.length < 3) { cerrar(); return; }

        temporizador = setTimeout(async function () {
            try {
                const datos = await pedirJSON('/api/buscar_lugar/?q=' + encodeURIComponent(texto));
                lista.innerHTML = '';
                if (!datos.resultados || datos.resultados.length === 0) {
                    lista.innerHTML = '<li>' + esc(datos.error || 'Sin resultados en Santiago') + '</li>';
                    lista.hidden = false;
                    return;
                }
                datos.resultados.forEach(function (r) {
                    const item = document.createElement('li');
                    item.textContent = r.nombre;
                    item.addEventListener('click', function () {
                        input.value = r.nombre;
                        alElegir({ lat: r.lat, lon: r.lon, texto: input.value });
                        cerrar();
                        dibujarPuntos();
                        mapa.setView([r.lat, r.lon], Math.max(mapa.getZoom(), 14));
                    });
                    lista.appendChild(item);
                });
                lista.hidden = false;
            } catch (error) {
                lista.innerHTML = '<li>No se pudo consultar el buscador</li>';
                lista.hidden = false;
            }
        }, 350);
    });
    document.addEventListener('click', function (e) { if (!lista.contains(e.target) && e.target !== input) { cerrar(); } });
}

crearBuscador('origen', 'lista-origen', function (lugar) { origen = lugar; });
crearBuscador('destino', 'lista-destino', function (lugar) { destino = lugar; });

el('btn-intercambiar').addEventListener('click', function () {
    const o = origen, d = destino, to = el('origen').value, td = el('destino').value;
    origen = d; destino = o;
    el('origen').value = td; el('destino').value = to;
    dibujarPuntos();
});

document.querySelectorAll('.medio').forEach(function (boton) {
    boton.addEventListener('click', function () {
        medio = boton.dataset.medio;
        document.querySelectorAll('.medio').forEach(function (b) { b.classList.toggle('activo', b === boton); });
        if (origen && destino && opciones.length > 0) { buscarRuta(); }
    });
});

function mostrarEstado(texto, esError) {
    const caja = el('estado');
    caja.hidden = !texto;
    caja.textContent = texto || '';
    caja.className = 'estado' + (esError ? ' error' : '');
}

el('form-ruta').addEventListener('submit', function (e) { e.preventDefault(); buscarRuta(); });

async function buscarRuta() {
    if (!origen || !destino) {
        mostrarEstado('Elige el origen y el destino de la lista de sugerencias.', true);
        return;
    }
    mostrarEstado('Buscando alternativas...');
    el('resultados').innerHTML = '';
    el('detalle').innerHTML = '';
    el('seguros-ruta').innerHTML = '';
    capaSeguros.clearLayers();
    avisoSeguros('');
    capaRuta.clearLayers();

    const parametros = 'lat1=' + origen.lat + '&lon1=' + origen.lon + '&lat2=' + destino.lat + '&lon2=' + destino.lon +
        '&medio=' + medio + '&origen=' + encodeURIComponent(origen.texto) + '&destino=' + encodeURIComponent(destino.texto);
    const url = (medio === 'micro' ? '/api/transporte/?' : '/api/calcular_ruta/?') + parametros;

    try {
        const datos = await pedirJSON(url);
        opciones = datos.opciones || [];
        if (!datos.exito || opciones.length === 0) {
            mostrarEstado(datos.mensaje || datos.error || 'No se encontraron alternativas.', true);
            return;
        }
        mostrarEstado('');
        indiceActivo = 0;
        dibujarPuntos();
        mostrarAlternativas();
        seleccionar(0);
        cargarHistorial();
    } catch (error) {
        mostrarEstado('No se pudo completar la búsqueda. Revisa tu conexión a internet.', true);
    }
}

function textoDistancia(m) { return m >= 1000 ? (m / 1000).toFixed(1).replace('.', ',') + ' km' : m + ' m'; }

function mostrarAlternativas() {
    const cont = el('resultados');
    cont.innerHTML = '';
    opciones.forEach(function (op, i) {
        const tarjeta = document.createElement('div');
        tarjeta.className = 'alternativa' + (i === indiceActivo ? ' activa' : '');
        let etiquetas = '';
        if (op.mas_segura) { etiquetas += '<span class="etiqueta segura">Más segura</span>'; }
        if (op.mas_rapida) { etiquetas += '<span class="etiqueta">Más rápida</span>'; }
        const tercera = (medio === 'micro')
            ? '<div class="metrica"><span>Transbordos</span><strong>' + op.trasbordos + '</strong></div>'
            : '<div class="metrica"><span>Distancia</span><strong>' + textoDistancia(op.distancia_m) + '</strong></div>';
        tarjeta.innerHTML =
            '<div class="alt-cabecera"><span class="alt-titulo">' + esc(op.titulo) + '</span><span class="etiquetas">' + etiquetas + '</span></div>' +
            '<div class="metricas">' +
            '<div class="metrica"><span>Tiempo</span><strong>' + horas(op.tiempo_min) + '</strong></div>' + tercera +
            '<div class="metrica"><span>Riesgo</span><strong class="nivel-' + op.nivel_riesgo + '">' + op.indice_riesgo + ' · ' + op.nivel_riesgo + '</strong></div>' +
            '</div>' +
            '<div class="barra"><div class="fondo-' + op.nivel_riesgo + '" style="width:' + Math.max(op.indice_riesgo, 3) + '%"></div></div>';
        tarjeta.addEventListener('click', function () { seleccionar(i); });
        cont.appendChild(tarjeta);
    });
}

function seleccionar(i) {
    indiceActivo = i;
    mostrarAlternativas();
    capaRuta.clearLayers();
    const op = opciones[i];
    let limites = null;

    if (medio === 'micro') {
        limites = dibujarMicro(op);
    } else {
        const color = COLOR_NIVEL[op.nivel_riesgo];
        L.polyline(op.coordenadas, { color: '#ffffff', weight: 9, opacity: 0.9 }).addTo(capaRuta);
        const linea = L.polyline(op.coordenadas, {
            color: medio === 'auto' ? '#2563a8' : color, weight: 5, opacity: 0.95,
            dashArray: medio === 'peaton' ? '8, 8' : null,
        }).addTo(capaRuta);
        limites = linea.getBounds();
    }
    if (limites) { mapa.fitBounds(limites, { padding: [40, 40] }); }
    mostrarDetalle(op);
}

function dibujarMicro(op) {
    const todos = [];
    function caminata(desde, hasta) {
        L.polyline([desde, hasta], { color: '#7b3fa0', weight: 3, dashArray: '4, 8' }).addTo(capaRuta);
    }
    let anterior = [origen.lat, origen.lon];
    op.tramos.forEach(function (t) {
        const color = t.color ? '#' + t.color : '#7b3fa0';
        caminata(anterior, [t.sube.lat, t.sube.lon]);
        L.polyline(t.trazado, { color: '#ffffff', weight: 9, opacity: 0.9 }).addTo(capaRuta);
        L.polyline(t.trazado, { color: '#7b3fa0', weight: 5, opacity: 0.95 }).addTo(capaRuta);
        const medioDelTrazado = t.trazado[Math.floor(t.trazado.length / 2)];
        L.marker(medioDelTrazado, { icon: L.divIcon({ className: '', html: '<span class="etiqueta-micro">' + esc(t.micro) + '</span>' }) }).addTo(capaRuta);
        L.circleMarker([t.sube.lat, t.sube.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#2e7d32', fillOpacity: 1 })
            .addTo(capaRuta).bindTooltip('Subir: ' + t.sube.nombre + ' (micro ' + t.micro + ')');
        L.circleMarker([t.baja.lat, t.baja.lon], { radius: 7, color: '#fff', weight: 2, fillColor: '#c62828', fillOpacity: 1 })
            .addTo(capaRuta).bindTooltip('Bajar: ' + t.baja.nombre + ' (micro ' + t.micro + ')');
        t.trazado.forEach(function (p) { todos.push(p); });
        anterior = [t.baja.lat, t.baja.lon];
    });
    caminata(anterior, [destino.lat, destino.lon]);
    todos.push([origen.lat, origen.lon], [destino.lat, destino.lon]);
    return L.latLngBounds(todos);
}

function mostrarDetalle(op) {
    let html = '<h3>Detalle de la alternativa</h3>';
    if (medio === 'micro') {
        html += '<ol class="pasos">';
        op.tramos.forEach(function (t, k) {
            html += '<li><strong>Micro ' + esc(t.micro) + '</strong>' + (t.destino ? ' hacia ' + esc(t.destino) : '') + '<br>' +
                'Subir en: ' + esc(t.sube.nombre) + '<br>Bajar en: ' + esc(t.baja.nombre) + '<br>' +
                t.n_paradas + ' paradas · viaje ' + horas(t.minutos_viaje) + (t.viaje_estimado ? ' (estimado, el GTFS no trae horas)' : ' (horario programado)') +
                ' · espera ' + horas(t.minutos_espera) + (t.espera_calculada_con_gtfs ? ' (según frecuencia programada)' : ' (supuesto)') +
                (t.sube.codigo ? '<br><button type="button" class="secundario pequeno" data-llegadas="' + esc(t.sube.codigo) + '" data-micro="' + esc(t.micro) + '">Ver llegadas en vivo</button><div class="llegadas-caja"></div>' : '') + '</li>';
            if (k < op.tramos.length - 1) {
                html += '<li>Caminar unos ' + op.caminata_trasbordo + ' m hasta el paradero del transbordo.</li>';
            }
        });
        html += '</ol><p class="nota">Caminata total aproximada: ' + op.caminata_m + ' m en línea recta (no sigue las calles). ' +
            'Los tiempos salen del horario programado (GTFS). Con el botón puedes ver las llegadas en vivo del paradero.</p>';
    } else if (medio === 'auto') {
        html += '<p class="nota">Tiempo calculado por el servicio de rutas sin considerar tráfico.</p>';
    } else {
        html += '<p class="nota">Tiempo estimado caminando a 80 m por minuto.</p>';
    }

    html += '<h3>Exposición a zonas de riesgo</h3>';
    html += '<p>Índice <strong class="nivel-' + op.nivel_riesgo + '">' + op.indice_riesgo + ' (' + op.nivel_riesgo + ')</strong>' +
        ' · ' + op.pct_zona_alta + '% del trayecto en zonas de nivel alto.</p>';
    if (op.zonas_en_ruta.length === 0) {
        html += '<p class="nota">El trayecto no pasa por zonas registradas.</p>';
    } else {
        html += '<ul>';
        op.zonas_en_ruta.slice(0, 6).forEach(function (z) {
            html += '<li>' + esc(z.sector) + ': nivel ' + esc(z.nivel_riesgo) + ', unos ' + z.metros + ' m' +
                (z.tipo_zona === 'ejemplo' ? ' <em>(dato simulado)</em>' : '') + '</li>';
        });
        html += '</ul>';
    }
    html += '<p class="nota">El índice (0 a 100) compara alternativas entre sí con los datos disponibles. No es la probabilidad de sufrir un delito.</p>';

    if (opciones.length > 1) {
        const segura = opciones.find(function (o) { return o.mas_segura; });
        html += '<p class="nota">Según los datos disponibles, la alternativa más segura es <strong>' + esc(segura.titulo) +
            '</strong> (índice ' + segura.indice_riesgo + ', ' + horas(segura.tiempo_min) + ').</p>';
    }
    el('detalle').innerHTML = html;
    segurosDeLaRuta(op);
    el('detalle').querySelectorAll('[data-llegadas]').forEach(function (b) {
        b.addEventListener('click', function () {
            cargarLlegadas(b.dataset.llegadas, b.dataset.micro, b.nextElementSibling);
        });
    });
}

async function cargarHistorial() {
    try {
        const datos = await pedirJSON('/api/historial/');
        const lista = el('historial');
        lista.innerHTML = '';
        if (datos.historial.length === 0) {
            lista.innerHTML = '<li class="nota">Aún no hay búsquedas.</li>';
            return;
        }
        datos.historial.forEach(function (h) {
            const item = document.createElement('li');
            item.innerHTML = esc(h.origen_texto) + ' &rarr; ' + esc(h.destino_texto) +
                '<small>' + esc(h.fecha) + ' · ' + esc(h.medio) + ' · riesgo ' + h.riesgo + ' · ' + horas(h.tiempo) + '</small>';
            item.addEventListener('click', function () {
                origen = { lat: h.origen[0], lon: h.origen[1], texto: h.origen_texto };
                destino = { lat: h.destino[0], lon: h.destino[1], texto: h.destino_texto };
                el('origen').value = h.origen_texto;
                el('destino').value = h.destino_texto;
                medio = h.medio;
                document.querySelectorAll('.medio').forEach(function (b) { b.classList.toggle('activo', b.dataset.medio === medio); });
                buscarRuta();
            });
            lista.appendChild(item);
        });
    } catch (error) {  }
}

let temporizadorMicro = null;
el('buscar-micro').addEventListener('input', function () {
    clearTimeout(temporizadorMicro);
    const texto = el('buscar-micro').value.trim();
    const lista = el('lista-micros');
    if (!texto) { lista.innerHTML = ''; return; }
    temporizadorMicro = setTimeout(async function () {
        const datos = await pedirJSON('/api/micros/?q=' + encodeURIComponent(texto));
        lista.innerHTML = '';
        if (datos.recorridos.length === 0) {
            lista.innerHTML = '<li class="nota">Sin resultados. ¿Ya importaste el GTFS?</li>';
            return;
        }
        datos.recorridos.forEach(function (r) {
            const item = document.createElement('li');
            item.innerHTML = '<strong>' + esc(r.numero) + '</strong> ' + esc(r.nombre) + '<br>';
            r.sentidos.forEach(function (s) {
                const boton = document.createElement('button');
                boton.type = 'button';
                boton.textContent = 'Hacia ' + (s.destino || 'sentido ' + s.id);
                boton.addEventListener('click', function () { alternarMicro(s.id); });
                item.appendChild(boton);
            });
            const vivo = document.createElement('button');
            vivo.type = 'button';
            vivo.textContent = 'Ver buses en vivo';
            const aviso = document.createElement('div');
            aviso.className = 'nota';
            vivo.addEventListener('click', function () { mostrarBuses(r.numero, aviso); });
            item.appendChild(vivo);
            item.appendChild(aviso);
            lista.appendChild(item);
        });
    }, 300);
});

async function alternarMicro(idSentido) {
    if (microsEnMapa[idSentido]) {
        capaMicros.removeLayer(microsEnMapa[idSentido]);
        delete microsEnMapa[idSentido];
        return;
    }
    const datos = await pedirJSON('/api/sentido/' + idSentido + '/');
    const grupo = L.layerGroup();
    const color = datos.color ? '#' + datos.color : '#7b3fa0';
    if (datos.trazado.length > 1) {
        const linea = L.polyline(datos.trazado, { color: '#7b3fa0', weight: 4, opacity: 0.85 }).addTo(grupo);
        linea.bindTooltip('Micro ' + datos.numero + ' hacia ' + datos.destino, { sticky: true });
        const medioDelTrazado = datos.trazado[Math.floor(datos.trazado.length / 2)];
        L.marker(medioDelTrazado, { icon: L.divIcon({ className: '', html: '<span class="etiqueta-micro">' + esc(datos.numero) + '</span>' }) }).addTo(grupo);
        mapa.fitBounds(linea.getBounds(), { padding: [40, 40] });
    }
    datos.paradas.forEach(function (p) {
        L.circleMarker([p.lat, p.lon], { radius: 3, color: '#7b3fa0', weight: 1, fillColor: '#fff', fillOpacity: 1 })
            .addTo(grupo).bindTooltip(p.nombre);
    });
    grupo.addTo(capaMicros);
    microsEnMapa[idSentido] = grupo;
}

el('btn-quitar-micros').addEventListener('click', function () {
    capaMicros.clearLayers();
    capaBuses.clearLayers();
    Object.keys(microsEnMapa).forEach(function (k) { delete microsEnMapa[k]; });
});

async function cargarParaderos() {
    capaParaderos.clearLayers();
    const aviso = el('info-paraderos');
    if (!el('chk-paraderos').checked) { aviso.textContent = ''; return; }
    if (mapa.getZoom() < 16) { aviso.textContent = 'Acerca el mapa (zoom 16 o más) para ver los paraderos.'; return; }
    const b = mapa.getBounds();
    const datos = await pedirJSON('/api/paraderos/?sur=' + b.getSouth() + '&norte=' + b.getNorth() + '&oeste=' + b.getWest() + '&este=' + b.getEast());
    aviso.textContent = datos.paraderos.length + ' paraderos en pantalla (GTFS DTPM).';
    datos.paraderos.forEach(function (p) {
        const marcador = L.circleMarker([p.lat, p.lon], { radius: 5, color: '#1f3a5f', weight: 1.5, fillColor: '#fff', fillOpacity: 1 }).addTo(capaParaderos);
        marcador.bindTooltip(p.nombre);
        marcador.on('click', async function () {
            const info = await pedirJSON('/api/parada/' + p.id + '/');
            const caja = document.createElement('div');
            caja.innerHTML = '<strong>' + esc(info.nombre) + '</strong><br>Micros: ' +
                (info.micros.length ? esc(info.micros.join(', ')) : 'sin datos') + '<br>';
            const boton = document.createElement('button');
            boton.type = 'button';
            boton.className = 'secundario pequeno';
            boton.textContent = 'Ver llegadas en vivo';
            const salida = document.createElement('div');
            boton.addEventListener('click', function () { cargarLlegadas(info.codigo, '', salida); });
            caja.appendChild(boton);
            caja.appendChild(salida);
            marcador.bindPopup(caja).openPopup();
        });
    });
}
mapa.on('moveend', function () { if (el('chk-paraderos').checked) { cargarParaderos(); } });

async function cargarFuentes() {
    const datos = await pedirJSON('/api/fuentes/');
    let html = '';
    if (datos.delitos) {
        html += '<p><strong>Delitos:</strong> ' + esc(datos.delitos.nombre) + '<br>Período: ' + esc(datos.delitos.periodo) +
            '<br>Actualizado: ' + esc(datos.delitos.actualizado) + '<br><em>' + esc(datos.delitos.notas) + '</em></p>';
    } else {
        html += '<p><strong>Delitos:</strong> sin estadísticas importadas. Se muestran zonas de EJEMPLO simuladas. ' +
            'Importa datos reales con <code>python manage.py importar_estadisticas</code> (ver README).</p>';
    }
    if (datos.gtfs) {
        html += '<p><strong>Micros:</strong> ' + esc(datos.gtfs.nombre) + '<br>Versión: ' + esc(datos.gtfs.version) +
            '<br>' + datos.gtfs_recorridos + ' recorridos, ' + datos.gtfs_paraderos + ' paraderos<br>Importado: ' + esc(datos.gtfs.actualizado) +
            '<br><em>' + esc(datos.gtfs.notas) + '</em></p>';
    } else if (datos.importando) {
        html += '<p><strong>Micros:</strong> importando el GTFS del DTPM. Esto tarda unos minutos y se hace solo; la página se actualizará cuando termine.</p>';
        setTimeout(cargarFuentes, 6000);
    } else if (datos.error_importacion) {
        html += '<p><strong>Micros:</strong> no se pudo importar: ' + esc(datos.error_importacion) +
            '<br>Ejecuta <code>python manage.py importar_gtfs</code> y mira el mensaje de error.</p>';
    } else {
        html += '<p><strong>Micros:</strong> sin GTFS importado. Ejecuta <code>python manage.py importar_gtfs</code>.</p>';
    }
    html += '<p class="nota">Llegadas y buses en vivo vienen de servicios externos (api-red / transantiago-api) y pueden no estar disponibles. Los tiempos de las rutas son horarios programados del GTFS.</p>';
    el('fuentes').innerHTML = html;
}

const capaSeguros = L.layerGroup().addTo(mapa);
const estadoSeguros = L.control({ position: 'bottomleft' });
estadoSeguros.onAdd = function () {
    const div = L.DomUtil.create('div', 'estado-seguros');
    div.hidden = true;
    return div;
};
estadoSeguros.addTo(mapa);
function avisoSeguros(texto) {
    const div = estadoSeguros.getContainer();
    div.hidden = !texto;
    div.textContent = texto || '';
}

const ICONO_SEGURO = '<svg viewBox="0 0 24 28" width="32" height="37"><path d="M12 1 2 5v8c0 6.5 4.2 11.3 10 14 5.8-2.7 10-7.5 10-14V5z" fill="#1b9e3e" stroke="#fff" stroke-width="2"/><path d="M7.5 14l3.2 3.4L16.8 10" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

function dibujarSeguros(lista) {
    capaSeguros.clearLayers();
    lista.forEach(function (l) {
        const texto = '<strong>' + esc(l.nombre) + '</strong><br>' + esc(l.categoria) + '<br>Lugar seguro a ' + l.metros + ' m';
        L.marker([l.lat, l.lon], {
            icon: L.divIcon({ className: 'marcador-seguro', html: ICONO_SEGURO, iconSize: [32, 37], iconAnchor: [16, 34] }),
            zIndexOffset: 1000,
        }).bindTooltip(texto, { direction: 'top', offset: [0, -30] }).bindPopup(texto).addTo(capaSeguros);
    });
}

const LETRA_SEGURO = { policia: 'C', hospital: 'H', bomberos: 'B', mall: 'M', super: 'S', metro: 'T', farmacia: 'F', publico: 'P' };

function listaSeguros(lista, destino, titulo, maximo) {
    let html = titulo ? '<h3>' + esc(titulo) + '</h3>' : '';
    if (lista.length === 0) {
        html += '<p class="nota">No se encontraron lugares seguros.</p>';
    } else {
        html += '<ul>';
        lista.slice(0, maximo).forEach(function (l, k) {
            html += '<li><span class="seguro seguro-' + l.tipo + '">' + LETRA_SEGURO[l.tipo] + '</span> ' +
                '<a href="#" data-k="' + k + '">' + esc(l.nombre) + '</a> <small>' + esc(l.categoria) + ' · a ' + textoDistancia(l.metros) + '</small></li>';
        });
        html += '</ul>';
        if (lista.length > maximo) { html += '<p class="nota">Y ' + (lista.length - maximo) + ' más, que se ven en el mapa.</p>'; }
    }
    destino.innerHTML = html;
    destino.querySelectorAll('a[data-k]').forEach(function (a) {
        a.addEventListener('click', function (ev) {
            ev.preventDefault();
            const l = lista[Number(a.dataset.k)];
            mapa.setView([l.lat, l.lon], 17);
        });
    });
}

function puntosDeLaRuta(op) {
    let puntos = [];
    if (medio === 'micro') {
        puntos.push([origen.lat, origen.lon]);
        op.tramos.forEach(function (t) { puntos = puntos.concat(t.trazado); });
        puntos.push([destino.lat, destino.lon]);
    } else {
        puntos = op.coordenadas;
    }
    const muestra = [puntos[0]];
    let ultimo = puntos[0];
    puntos.forEach(function (p) {
        if (L.latLng(ultimo).distanceTo(L.latLng(p)) >= 250) { muestra.push(p); ultimo = p; }
    });
    const fin = puntos[puntos.length - 1];
    if (muestra[muestra.length - 1] !== fin) { muestra.push(fin); }
    if (muestra.length > 60) {
        const paso = Math.ceil(muestra.length / 59);
        return muestra.filter(function (p, k) { return k % paso === 0 || k === muestra.length - 1; }).slice(0, 60);
    }
    return muestra;
}

function mezclarSeguros(a, b) {
    const lista = a.slice();
    b.forEach(function (x) {
        if (!lista.some(function (y) { return y.tipo === x.tipo && Math.abs(y.lat - x.lat) < 0.0015 && Math.abs(y.lon - x.lon) < 0.0015; })) { lista.push(x); }
    });
    return lista.sort(function (p, q) { return p.metros - q.metros; });
}

let numeroConsultaSeguros = 0;
async function segurosDeLaRuta(op) {
    const caja = el('seguros-ruta');
    const numero = ++numeroConsultaSeguros;
    capaSeguros.clearLayers();
    avisoSeguros('Buscando lugares seguros cerca de tu ruta...');
    caja.innerHTML = '<p class="nota">Buscando lugares seguros cerca de tu ruta...</p>';
    const puntos = puntosDeLaRuta(op).map(function (p) { return p[0].toFixed(5) + ',' + p[1].toFixed(5); }).join(';');
    const base = '/api/lugares_seguros/?ruta=' + encodeURIComponent(puntos);
    let lista = [];
    let lejos = false;
    try {
        const d = await pedirJSON(base);
        if (numero !== numeroConsultaSeguros) { return; }
        lista = d.lugares;
        lejos = d.lejos;
        dibujarSeguros(lista);
        listaSeguros(lista, caja, lejos ? 'Lugares seguros más cercanos a tu ruta' : 'Lugares seguros cerca de tu ruta', 8);
        if (lejos) { caja.innerHTML += '<p class="nota">No hay lugares seguros registrados a menos de ' + d.radio + ' m de esta ruta. Estos son los más cercanos.</p>'; }
        avisoSeguros(lista.length + (lejos ? ' lugares seguros más cercanos a tu ruta' : ' lugares seguros cerca de tu ruta'));
        if (d.sin_comisarias) { caja.innerHTML += '<p class="nota">Solo se ven 3 comisarías por ahora. Para ver todas: py manage.py importar_comisarias.</p>'; }
    } catch (error) {
        avisoSeguros('No se pudieron consultar los lugares seguros');
        caja.innerHTML = '<p class="nota">No se pudieron consultar los lugares seguros.</p>';
        return;
    }
    try {
        const d2 = await pedirJSON(base + '&fuente=internet');
        if (numero !== numeroConsultaSeguros || !d2.ok || d2.lugares.length === 0) { return; }
        const todos = lejos ? d2.lugares : mezclarSeguros(lista, d2.lugares);
        dibujarSeguros(todos);
        listaSeguros(todos, caja, 'Lugares seguros cerca de tu ruta', 8);
        avisoSeguros(todos.length + ' lugares seguros cerca de tu ruta');
    } catch (error) { }
}

function ubicacionActual() {
    const punto = origen ? { lat: origen.lat, lon: origen.lon } : { lat: mapa.getCenter().lat, lon: mapa.getCenter().lng };
    return { punto: punto, desde: origen ? 'tu punto de origen' : 'el centro del mapa' };
}

async function mostrarSegurosAlrededor(punto, desde) {
    const caja = el('lista-seguros-panico');
    caja.innerHTML = '<p class="nota">Buscando lugares seguros cerca...</p>';
    const base = '/api/lugares_seguros/?lat=' + punto.lat + '&lon=' + punto.lon + '&radio=1500';
    let lista = [];
    try {
        const d = await pedirJSON(base);
        lista = d.lugares;
        dibujarSeguros(lista);
        listaSeguros(lista, caja, 'Lugares seguros cerca de ' + desde, 8);
        if (d.lejos) { caja.innerHTML += '<p class="nota">No hay lugares registrados a menos de 1,5 km. Estos son los más cercanos.</p>'; }
        const puntos = lista.map(function (l) { return [l.lat, l.lon]; });
        puntos.push([punto.lat, punto.lon]);
        mapa.fitBounds(L.latLngBounds(puntos), { padding: [50, 50], maxZoom: 16 });
    } catch (error) {
        caja.innerHTML = '<p class="nota">No se pudieron consultar los lugares seguros.</p>';
        mapa.setView([punto.lat, punto.lon], 15);
        return;
    }
    try {
        const d2 = await pedirJSON(base + '&fuente=internet');
        if (!d2.ok || d2.lugares.length === 0) { return; }
        const todos = mezclarSeguros(lista, d2.lugares);
        dibujarSeguros(todos);
        listaSeguros(todos, caja, 'Lugares seguros cerca de ' + desde, 8);
    } catch (error) { }
}

el('btn-seguros').addEventListener('click', async function () {
    const u = ubicacionActual();
    mostrarSegurosAlrededor(u.punto, u.desde);
});

el('btn-panico').addEventListener('click', async function () {
    const u = ubicacionActual();
    const formulario = new FormData();
    formulario.append('lat', u.punto.lat);
    formulario.append('lon', u.punto.lon);
    const token = document.querySelector('meta[name="csrf-token"]').content;
    try {
        const datos = await pedirJSON('/api/panico/', { method: 'POST', body: formulario, headers: { 'X-CSRFToken': token } });
        el('estado-panico').textContent = datos.mensaje + ' Ubicación usada: ' + u.desde + '.';
        L.circleMarker([u.punto.lat, u.punto.lon], { radius: 14, color: '#c62828', fillColor: '#c62828', fillOpacity: 0.4 })
            .addTo(capaPuntos).bindPopup('Alerta registrada aquí');
    } catch (error) {
        el('estado-panico').textContent = 'No se pudo registrar la alerta.';
    }
    mostrarSegurosAlrededor(u.punto, 'donde registraste la alerta');
});

cargarZonas();
cargarFuentes();
cargarHistorial();
