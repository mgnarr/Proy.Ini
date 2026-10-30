from django.db import models

class ZonaRiesgo(models.Model):
    sector = models.CharField(max_length=150)
    calle_principal = models.CharField(max_length=150)
    comuna = models.CharField(max_length=80)
    lat = models.FloatField()
    lon = models.FloatField()
    radio_metros = models.IntegerField(default=450)
    delitos_reportados = models.IntegerField(default=0)
    tipo_delito_frecuente = models.CharField(max_length=200)
    iluminacion = models.IntegerField(default=3)
    nivel_riesgo = models.CharField(max_length=20)
    punto_resguardo_cercano = models.CharField(max_length=150)
    desvio_seguro_lat = models.FloatField()
    desvio_seguro_lon = models.FloatField()
    nombre_desvio = models.CharField(max_length=150)
    fecha_actualizacion = models.DateField(auto_now=True)

    def __str__(self):
        return f"{self.sector} ({self.nivel_riesgo})"

class SolicitudRuta(models.Model):
    origen_lat = models.FloatField()
    origen_lon = models.FloatField()
    destino_lat = models.FloatField()
    destino_lon = models.FloatField()
    origen_texto = models.CharField(max_length=200, blank=True)
    destino_texto = models.CharField(max_length=200, blank=True)
    medio_transporte = models.CharField(max_length=30)
    riesgo_calculado = models.IntegerField(default=0)
    tiempo_estimado_min = models.IntegerField(default=0)
    fecha_hora = models.DateTimeField(auto_now_add=True)

class ContactoEmergencia(models.Model):
    nombre = models.CharField(max_length=100)
    telefono = models.CharField(max_length=30)
    relacion = models.CharField(max_length=50)

class BotonPanico(models.Model):
    estado = models.CharField(max_length=30, default="Activado")
    latitud = models.FloatField(null=True, blank=True)
    longitud = models.FloatField(null=True, blank=True)
    fecha_activacion = models.DateTimeField(auto_now_add=True)

class EstadisticaComuna(models.Model):
    comuna = models.CharField(max_length=80)
    comuna_clave = models.CharField(max_length=80, db_index=True)
    periodo = models.CharField(max_length=40)
    delitos = models.IntegerField()
    poblacion = models.IntegerField(null=True, blank=True)
    fuente = models.CharField(max_length=120)
    url_fuente = models.CharField(max_length=300, blank=True)

    def __str__(self):
        return f"{self.comuna} {self.periodo}: {self.delitos}"

class RegistroFuente(models.Model):
    clave = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=150)
    version = models.CharField(max_length=150, blank=True)
    periodo = models.CharField(max_length=80, blank=True)
    url = models.CharField(max_length=300, blank=True)
    notas = models.TextField(blank=True)
    fecha_importacion = models.DateTimeField(auto_now=True)

class Parada(models.Model):
    stop_id = models.CharField(max_length=40, unique=True)
    nombre = models.CharField(max_length=200)
    lat = models.FloatField(db_index=True)
    lon = models.FloatField(db_index=True)

class Recorrido(models.Model):
    route_id = models.CharField(max_length=40, unique=True)
    numero = models.CharField(max_length=30, db_index=True)
    nombre = models.CharField(max_length=250, blank=True)
    color = models.CharField(max_length=10, blank=True)

    def __str__(self):
        return self.numero

class Sentido(models.Model):
    recorrido = models.ForeignKey(Recorrido, on_delete=models.CASCADE, related_name="sentidos")
    direction_id = models.IntegerField(default=0)
    destino = models.CharField(max_length=200, blank=True)
    trazado = models.TextField(blank=True)
    n_viajes = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.recorrido.numero} sentido {self.direction_id}"

class SecuenciaParada(models.Model):
    sentido = models.ForeignKey(Sentido, on_delete=models.CASCADE, related_name="secuencia")
    parada = models.ForeignKey(Parada, on_delete=models.CASCADE)
    orden = models.IntegerField()
    segundos = models.IntegerField(null=True, blank=True)

    class Meta:
        ordering = ["orden"]
        indexes = [models.Index(fields=["sentido", "orden"])]
