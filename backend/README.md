# Partner Backend

Backend API for partner frontend (Django + DRF).

## Stack
- Django
- Django REST Framework
- PostgreSQL

## PostgreSQL env

Set these environment variables before running migrations/start:

```powershell
$env:POSTGRES_DB="mysub"
$env:POSTGRES_USER="postgres"
$env:POSTGRES_PASSWORD="postgres"
$env:POSTGRES_HOST="127.0.0.1"
$env:POSTGRES_PORT="5432"
```

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```
