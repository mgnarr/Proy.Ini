
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-e4q79f104akl)1!y)gsw)lym4__mo7t_ty9=_2q$ow1o*h*!d3'

DEBUG = True

ALLOWED_HOSTS = []

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'mapa_app',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'RutaSegura.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'RutaSegura.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'es-cl'

TIME_ZONE = 'America/Santiago'

USE_I18N = True

USE_TZ = True

STATIC_URL = 'static/'

MAILERS = {
    'default': {
        'BACKEND': 'django.core.mail.backends.console.EmailBackend',
    },
}

GTFS_PAGINA_DTPM = 'https://dtpm.cl/index.php/gtfs-vigente'
GTFS_URL_RESPALDO = 'https://dtpm.cl/descargas/gtfs/GTFS_20261003.zip'
GTFS_CARPETA = BASE_DIR / 'datos' / 'gtfs'

NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'
PHOTON_URL = 'https://photon.komoot.io/api/'
LLEGADAS_URL = 'https://api.xor.cl/red/bus-stop'
OVERPASS_URLS = ['https://overpass-api.de/api/interpreter', 'https://overpass.kumi.systems/api/interpreter',
                 'https://overpass.private.coffee/api/interpreter']
BUSES_URL = 'https://api.scltrans.it/v1/buses'

SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
USER_AGENT = 'RutaSeguraSantiago/1.0 (proyecto academico IWG400)'

RUTEO_URLS = {
    'peaton': ['https://routing.openstreetmap.de/routed-foot/route/v1/driving'],
    'auto': ['https://routing.openstreetmap.de/routed-car/route/v1/driving',
             'https://router.project-osrm.org/route/v1/driving'],
}
