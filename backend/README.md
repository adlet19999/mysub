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

## Password reset by email (Gmail)

Copy `.env.example` to `.env` and set the SMTP variables:

```powershell
FRONTEND_PARTNER_BASE_URL=http://localhost:3000
DJANGO_EMAIL_HOST=smtp.gmail.com
DJANGO_EMAIL_PORT=587
DJANGO_EMAIL_USE_TLS=true
DJANGO_EMAIL_HOST_USER=your-project-mail@gmail.com
DJANGO_EMAIL_HOST_PASSWORD=your-16-character-gmail-app-password
DJANGO_DEFAULT_FROM_EMAIL=your-project-mail@gmail.com
```

For Gmail, use App Password (not your main account password).
