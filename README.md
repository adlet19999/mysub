# MySub (Partner Only)

This workspace currently contains:
- frontend partner app: `frontend/web-partner`
- backend API: `backend`

## Start PostgreSQL (Docker)

```powershell
docker compose up -d postgres
```

## Start backend

```powershell
cd backend
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
# migrate также загрузит полный справочник: категории, услуги и виды услуг
python manage.py runserver
```

## Create tables (separate command)

```powershell
cd backend
py -3.14 manage.py makemigrations
py -3.14 manage.py migrate
```

## Start partner frontend

```powershell
cd frontend/web-partner
Copy-Item .env.local.example .env.local
npm run dev
```

Open: `http://localhost:3000/partner`

## Production Deploy (Ubuntu + Docker)

### 1) Prepare repository on server

```bash
cd /opt/apps
git clone <YOUR_GITHUB_REPO_URL> mysub
cd mysub
cp .env.prod.example .env.prod
```

Edit `.env.prod` and set strong passwords/secrets and your domain/IP.

### 2) Start services

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml ps
```

### 3) Check logs

```bash
docker compose -f docker-compose.prod.yml logs -f --tail=200
```

### 4) Open app

Use `http://SERVER_IP/partner`.

### Optional HTTPS (if domain exists)

```bash
sudo apt install -y nginx certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com -d www.your-domain.com
```
