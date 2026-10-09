# Partner Backend

Backend API for partner frontend (Django + DRF).

## Stack
- Django
- Django REST Framework
- PostgreSQL

## Booking prices and availability

- Working hours, breaks and occupied places determine available booking slots.
  Discount windows do not restrict availability outside those windows.
- A service discount applies only when its entire duration fits a specialist's
  discount window and the customer's subscription is active and valid through
  the visit date (inclusive). Missing, paused or expired subscriptions and
  inactive customer accounts pay the full service price.
- Partner bookings identify the customer by normalized phone; mobile bookings
  use the authenticated customer's phone. The client cannot grant a discount.
- Prices are stored per participant, including for group sessions. Moving a
  booking or changing its customer recalculates the price; status-only updates
  preserve the stored price. Existing bookings are not repriced on deployment.
- CRM creation and rescheduling reject past times. ISO timestamps without an
  offset are interpreted in the configured application timezone.
- New CRM booking phones are normalized. Admin history and completed-visit
  totals also recognize legacy formatted phone numbers.
- Admin and partner turnover use stored prices of completed visits, not current
  service prices or amounts of cancelled bookings/no-shows. These are visit
  totals, not confirmation of a payment provider transaction.
- In the calendar, create the first group booking with "Add booking"; subsequent
  clients can be added from that group's details. The participant form keeps the
  service, specialist and start time fixed; the server checks subscription,
  duplicate bookings and capacity again when saving.

## Launch regression checks

Run the complete Django test suite against a disposable PostgreSQL test database:

```bash
python manage.py test --noinput
```

The PostgreSQL account must be able to create a test database. Do not point test
settings at a production database or reuse a production database as a test
database. Mobile authentication tests require the test SMS code and token TTL
settings described in the project configuration; do not use real SMS delivery.
`partner_api.test_lifecycle` includes API registration-to-completion scenarios,
subscription/window pricing, individual/group capacity, cancellation,
rescheduling, validation and concurrent last-place booking.

See [the launch audit](../CRM-LAUNCH-AUDIT.md) for measured results and remaining
launch blockers. A passing regression suite does not certify every UI control
or external payment/SMS/email integration.

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
