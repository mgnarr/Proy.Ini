RUTA SEGURA (equipo 10). COMO INSTALARLO (WINDOWS)

Necesitas tener Python 3.12 o más nuevo (se baja de python.org, y al instalarlo hay que marcar "Add python.exe to PATH"). También necesitas internet, porque el mapa y los buscadores usan servicios de afuera.

Descomprimir el zip, entrar a la carpeta donde está el archivo manage.py y hacer doble clic en iniciar.bat. Ese archivo hace todos los pasos de abajo solo.

Si lo quieres hacer a mano, abre una terminal (cmd) dentro de esa misma carpeta. Puedes escribir cmd en la barra de arriba (donde sale la ruta) y apretar Enter. Después se escriben estos comandos, uno por uno:

py -m venv venv
venv\\Scripts\\activate
pip install -r requirements.txt
py manage.py makemigrations mapa\_app
py manage.py migrate
py manage.py runserver

Cuando salga "Starting development server at http://127.0.0.1:8000/" hay que abrir esa dirección en el navegador. La terminal tiene que quedar abierta mientras se usa la página. Para apagar el servidor se aprieta Ctrl+C.

Importante: la página se abre con esa dirección. Si se abre el archivo index.html directo desde la carpeta se ve sin estilos y no funciona.

Cuando el entorno ya está creado, para volver a usar la aplicacion solo hacen falta estos dos comandos:

venv\\Scripts\\activate
py manage.py runserver



DEPENDENCIAS

* Python 3.12 o más nuevo.
* Django 6.1.2. Es la única librería de Python se instala con pip install -r requirements.txt (los comandos están arriba).
* Internet, para el mapa (Leaflet y los cuadros del mapa), el buscador de direcciones y las rutas a pie y en auto.
* La base de datos es SQLite, viene con Python y se crea sola con py manage.py migrate. No hay que instalar nada más.

PROBLEMAS QUE PUEDEN SALIR

* Dice "Python was not found": en Windows a veces "python" abre la Microsoft Store. Usar "py" en vez de "python", o instalar Python desde python.org marcando "Add python.exe to PATH".
* "El sistema no puede encontrar la ruta especificada" al hacer venv\\Scripts\\activate: todavía no se creó el entorno. Primero hay que correr py -m venv venv, y hay que estar dentro de la carpeta del proyecto (donde está manage.py).
* "Could not open requirements file": la terminal está en otra carpeta. Hay que entrar a la carpeta donde está requirements.txt.
* La página se ve sin diseño: no se abrió con http://127.0.0.1:8000/ sino el archivo directo.
* El mapa sale con cuadros que dicen "Access blocked" o "API key": reiniciar el servidor y recargar con Ctrl+F5.
* El puerto 8000 está ocupado: py manage.py runserver 8080 y abrir http://127.0.0.1:8080/.
* "No such table": falta correr py manage.py makemigrations mapa\_app y después py manage.py migrate.
* El autocompletado no muestra nada: hay que escribir al menos 3 letras. Si sigue sin salir, el servicio puede estar caído, esperar un rato.
* "Todavía no se importó el GTFS": esperar a que termine la importación automática o correr py manage.py importar\_gtfs.
* Para correr las pruebas: py manage.py test



