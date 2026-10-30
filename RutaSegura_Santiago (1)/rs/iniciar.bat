@echo off
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat py -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
python manage.py makemigrations mapa_app
python manage.py migrate
python manage.py importar_gtfs --si-falta
if not exist datos\comisarias.json python manage.py importar_comisarias
python manage.py runserver
pause
