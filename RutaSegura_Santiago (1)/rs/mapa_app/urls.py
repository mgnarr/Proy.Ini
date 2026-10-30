from django.urls import path
from . import views

urlpatterns = [
    path('', views.index_view, name='index'),
    path('api/calcular_ruta/', views.api_calcular_ruta, name='api_calcular_ruta'),
    path('api/transporte/', views.api_transporte, name='api_transporte'),
    path('api/zonas/', views.api_zonas, name='api_zonas'),
    path('api/fuentes/', views.api_fuentes, name='api_fuentes'),
    path('api/buscar_lugar/', views.api_buscar_lugar, name='api_buscar_lugar'),
    path('api/micros/', views.api_micros, name='api_micros'),
    path('api/sentido/<int:sentido_id>/', views.api_sentido, name='api_sentido'),
    path('api/paraderos/', views.api_paraderos, name='api_paraderos'),
    path('api/parada/<int:parada_id>/', views.api_parada, name='api_parada'),
    path('api/llegadas/<str:codigo>/', views.api_llegadas, name='api_llegadas'),
    path('api/lugares_seguros/', views.api_lugares_seguros, name='api_lugares_seguros'),
    path('api/buses/', views.api_buses, name='api_buses'),
    path('api/historial/', views.api_historial, name='api_historial'),
    path('api/panico/', views.api_panico, name='api_panico'),
]
