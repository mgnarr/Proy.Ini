RUTA SEGURA SANTIAGO

Proyecto del ramo IWG400 Proyecto Inicial (USM), equipo 10.

Es una página web hecha con Django donde uno escribe un origen y un destino en Santiago y la página muestra distintas rutas (a pie, en auto o en micro). Cada ruta tiene su tiempo, distancia y un índice de riesgo, y se marca cuál es la más segura y cuál la más rápida. También hay un mapa de calor con zonas de riesgo y un botón de pánico.


QUE HAY EN LA PAGINA

- Planificar ruta: se escribe el origen y el destino (con autocompletado), se elige a pie, micro o auto y se aprieta "Buscar ruta". Abajo salen las alternativas y al hacer clic en una se dibuja en el mapa. También guarda las últimas búsquedas.
- Mapa de calor: muestra las zonas según su nivel de riesgo (bajo, medio, alto). Se pueden prender y apagar capas y ver el recorrido de una micro por su número.
- Botón de pánico: guarda la ubicación en la base de datos. No manda mensajes a nadie. Al registrar la alerta, la página muestra en el mapa y en una lista los lugares seguros que hay cerca de ese punto.
- Lugares seguros: comisarías, hospitales, bomberos, centros comerciales, supermercados, Metro y farmacias. Solo se muestran los que están cerca de la ruta elegida (a menos de 400 metros de ella) y los que están cerca de la ubicación de la persona.


COMO INSTALARLO (WINDOWS)

Necesitas tener Python 3.12 o más nuevo (se baja de python.org, y al instalarlo hay que marcar "Add python.exe to PATH"). También necesitas internet, porque el mapa y los buscadores usan servicios de afuera.

Lo más fácil: descomprimir el zip, entrar a la carpeta donde está el archivo manage.py y hacer doble clic en iniciar.bat. Ese archivo hace todos los pasos de abajo solo.

Si lo quieres hacer a mano, abre una terminal (cmd) dentro de esa misma carpeta. Una forma fácil es abrir la carpeta en el explorador, escribir cmd en la barra de arriba (donde sale la ruta) y apretar Enter. Después se escriben estos comandos, uno por uno:

py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
py manage.py makemigrations mapa_app
py manage.py migrate
py manage.py runserver

Cuando salga "Starting development server at http://127.0.0.1:8000/" hay que abrir esa dirección en el navegador. La terminal tiene que quedar abierta mientras se usa la página. Para apagar el servidor se aprieta Ctrl+C.

Importante: la página se abre con esa dirección. Si se abre el archivo index.html directo desde la carpeta se ve sin estilos y no funciona.

Cuando el entorno ya está creado, para volver a usar el proyecto solo hacen falta estos dos comandos:

venv\Scripts\activate
py manage.py runserver


DEPENDENCIAS

- Python 3.12 o más nuevo.
- Django 6.1.2. Es la única librería de Python y está en requirements.txt, por eso se instala con pip install -r requirements.txt (los comandos están arriba).
- Internet, para el mapa (Leaflet y los cuadros del mapa), el buscador de direcciones y las rutas a pie y en auto.
- La base de datos es SQLite, viene con Python y se crea sola con py manage.py migrate. No hay que instalar nada más.


DATOS QUE VIENEN EN EL PROYECTO PARA PROBAR

- datos/gtfs/GTFS_20261003.zip: recorridos, paraderos y trazados de las micros (DTPM). Se importa solo la primera vez que se abre la página (o con py manage.py importar_gtfs).
- datos/crimenes_santiago.json: zonas de riesgo de ejemplo (simuladas) para que el mapa de calor y el índice de riesgo funcionen sin tener que descargar nada.
- datos/comunas_santiago.geojson: límites de las comunas, para aceptar solo direcciones de Santiago.
- datos/lugares_seguros.json: lugares seguros sacados del GTFS (Metro, hospitales, centros comerciales, etc.). Ya viene hecho.
- datos/comisarias.json: la lista completa de comisarías se genera con py manage.py importar_comisarias (hace falta internet esa primera vez).

No hace falta bajar ni cargar nada más para probar la página.


COMO PROBAR LA FUNCIONALIDAD PRINCIPAL (BUSCAR UNA RUTA Y COMPARARLAS)

1. Con el servidor andando, abrir http://127.0.0.1:8000/
2. En "Planificar ruta" escribir el origen, por ejemplo Plaza de Armas, y elegir una opción de la lista que aparece. Escribir el destino, por ejemplo Estación Central o Los Leones (Providencia), y también elegirlo de la lista.
3. Elegir "A pie", "Micro" o "Auto" y apretar "Buscar ruta".
4. Aparecen las alternativas con tiempo, distancia e índice de riesgo. Una dice "Más segura" y otra "Más rápida". Al hacer clic en una se dibuja en el mapa y abajo se ve el detalle (en micro: qué micro tomar, dónde subir y bajar, y el botón de llegadas en vivo).
5. En "Mapa de calor" se pueden prender o apagar las zonas de riesgo, y en "Botón de pánico" se registra una alerta.

Con el GTFS que viene en el proyecto, de Plaza de Armas a Estación Central en micro salen alternativas directas y con un transbordo (lo revisamos con la lógica del proyecto, usando el archivo real). Para que se vean todas las pantallas hay que abrirlo en un computador con internet.


MICROS (GTFS)

Los datos de las micros salen del GTFS del DTPM (Red Movilidad). El proyecto ya trae el archivo en datos/gtfs/GTFS_20261003.zip. La primera vez que se abre la página, si las micros no están cargadas, se importan solas y demora unos minutos. En "Mapa de calor", abajo en Fuentes, aparece si está importando o si ya terminó.

También se puede importar a mano con este comando:

py manage.py importar_gtfs

Si el DTPM saca una versión nueva, se descarga el zip desde https://dtpm.cl/index.php/gtfs-vigente, se deja en datos/gtfs y se vuelve a correr el comando (o se usa py manage.py importar_gtfs --zip RUTA_DEL_ZIP). Solo se cargan las micros, no el Metro ni los trenes.

Con eso la página busca micros directas o con un transbordo entre paraderos que estén a menos de 500 metros del origen y del destino. El tiempo es caminata + espera + viaje. La espera y el viaje salen de los horarios programados del GTFS, no de dónde están las micros en ese momento.

Además hay dos botones que consultan las llegadas y la posición de los buses en vivo. Usamos como base las APIs de los proyectos api-red (api.xor.cl/red/bus-stop) y transantiago-api (api.scltrans.it). Son servicios de otras personas, así que a veces pueden no responder. Si no responden, la página avisa y sigue funcionando con los horarios del GTFS.


ZONAS DE RIESGO Y DATOS DE DELITOS

Por ahora el mapa muestra zonas de ejemplo (datos/crimenes_santiago.json). Son datos inventados para poder mostrar el funcionamiento, y en la página aparecen marcadas como "dato simulado". No son estadísticas reales.

Para usar datos reales hay que bajar una tabla de delitos por comuna del CEAD (cead.minsegpublica.gob.cl) o del Observatorio Público (observatoriopublico.cl) y cargarla con:

py manage.py importar_estadisticas --archivo RUTA_DEL_ARCHIVO.csv --fuente "CEAD" --periodo "2025"

El archivo tiene que tener una columna con la comuna y otra con la cantidad de delitos (datos/plantilla_estadisticas_comunales.csv muestra el formato; también sirve .json, o se puede usar --url con un enlace). Al importar se muestra la fuente, el período y la fecha de actualización en la página, y las zonas de ejemplo se reemplazan por las comunas reales. Estos datos son por comuna, así que no dicen en qué calle pasó cada delito.


INDICE DE RIESGO

Cada tramo de una ruta se asocia a la zona más cercana y toma su nivel (bajo = 1, medio = 2, alto = 3). El índice es el promedio de esos niveles según los metros de cada tramo, y se pasa a una escala de 0 a 100. Sirve para comparar rutas entre sí. No es la probabilidad de que a alguien le pase algo.


BUSCADOR DE CALLES

Las calles se buscan de tres formas a la vez. La primera usa los nombres de los paraderos del GTFS (por ejemplo "Vicuña Mackenna con San Miguel"), así que funciona aunque no haya internet y aunque se escriba mal el nombre (por ejemplo "vicuña makena"). Las otras dos son Photon y Nominatim, que sirven para direcciones con número y lugares. Solo se aceptan resultados dentro de las comunas del Gran Santiago, usando el archivo datos/comunas_santiago.geojson (sacado del repositorio Chile-GeoJSON; son contornos simplificados, así que cerca de los bordes puede ser aproximado).

Ese archivo Chile-GeoJSON trae solo los límites de las comunas, no las calles.


LUGARES SEGUROS

Se muestran los lugares seguros que están a menos de 500 metros de la ruta elegida (en el mapa con un escudo verde, y en una lista debajo del detalle; cambian al elegir otra alternativa). Si cerca de la ruta no hay ninguno, la página muestra los más cercanos y avisa. En Botón de pánico, al registrar la alerta (o con "Buscar lugares seguros") se muestran los que hay cerca de ese punto, que es el origen que se puso o, si no hay origen, el centro del mapa. La página no pide la ubicación del navegador.

Los lugares vienen de dos fuentes:

1. El mismo GTFS del DTPM (funciona sin internet y sale al tiro, el archivo se llama datos/lugares_seguros.json y se arma solo con importar_gtfs). De ahí salen las 126 estaciones de Metro, hospitales y centros de salud (CESFAM, CECOSF), centros comerciales, algunos supermercados, municipalidades, universidades, plazas y terminales principales, y las pocas comisarías y retenes que aparecen como referencia en los paraderos. Las ubicaciones son las de los paraderos que están junto a cada lugar, o sea son aproximadas (unos cien metros).
2. OpenStreetMap (API Overpass), que necesita internet y se agrega después de que ya apareció lo anterior. Trae hospitales, bomberos, centros comerciales, supermercados, Metro y farmacias cerca de la ruta. Las comisarías completas del Gran Santiago se bajan una vez con py manage.py importar_comisarias (también se descargan solas al abrir la página, en segundo plano) y se guardan en datos/comisarias.json. Antes de esa descarga solo aparecen las comisarías que trae el GTFS.

Las letras en las listas son: C comisaría, H hospital o centro de salud, B bomberos, M centro comercial, S supermercado, T Metro, F farmacia, P lugar público concurrido. Los datos pueden estar incompletos (el GTFS no trae todas las comisarías ni todos los hospitales). Que un lugar aparezca no asegura que esté abierto ni que el sector sea seguro, es solo una referencia.


SERVICIOS QUE USA

No necesitan clave y se pueden usar gratis, pero dependen de internet:
- Mapa: Esri (si falla, OpenStreetMap). Leaflet se carga desde unpkg.
- Buscador de direcciones: Photon y Nominatim, solo para Santiago (más los paraderos del GTFS).
- Lugares seguros: Overpass (overpass-api.de). Las comisarías se bajan una sola vez.
- Rutas a pie y en auto: routing.openstreetmap.de (para auto también router.project-osrm.org).
- Micros en vivo: api.xor.cl y api.scltrans.it.

Las direcciones se pueden cambiar en RutaSegura/settings.py.


QUE FALTA O NO ES PERFECTO

- Las zonas de riesgo son de ejemplo hasta que se importen datos reales.
- Las rutas en micro usan horarios programados, y la caminata se calcula en línea recta (no sigue las calles).
- No se pudieron probar desde donde se hizo el proyecto los servicios de internet (mapa, buscador, rutas, micros en vivo y lugares seguros), así que conviene revisarlos en un computador con internet.
- Solo se buscan micros directas o con un transbordo.


PROBLEMAS QUE PUEDEN SALIR

- Dice "Python was not found": en Windows a veces "python" abre la Microsoft Store. Usar "py" en vez de "python", o instalar Python desde python.org marcando "Add python.exe to PATH".
- "El sistema no puede encontrar la ruta especificada" al hacer venv\Scripts\activate: todavía no se creó el entorno. Primero hay que correr py -m venv venv, y hay que estar dentro de la carpeta del proyecto (donde está manage.py).
- "Could not open requirements file": la terminal está en otra carpeta. Hay que entrar a la carpeta donde está requirements.txt.
- La página se ve sin diseño: no se abrió con http://127.0.0.1:8000/ sino el archivo directo.
- El mapa sale con cuadros que dicen "Access blocked" o "API key": reiniciar el servidor y recargar con Ctrl+F5.
- El puerto 8000 está ocupado: py manage.py runserver 8080 y abrir http://127.0.0.1:8080/.
- "No such table": falta correr py manage.py makemigrations mapa_app y después py manage.py migrate.
- El autocompletado no muestra nada: hay que escribir al menos 3 letras. Si sigue sin salir, el servicio puede estar caído, esperar un rato.
- "Todavía no se importó el GTFS": esperar a que termine la importación automática o correr py manage.py importar_gtfs.
- Para correr las pruebas: py manage.py test
