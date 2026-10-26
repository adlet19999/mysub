# Partner Backend

Backend API for partner frontend (Django + DRF).

## Stack
- Django
- Django REST Framework
- PostgreSQL

## Booking prices and availability

- Working hours, breaks and occupied places determine available booking slots.
  Discount windows do not restrict availability outside those windows.
- A service discount applies only to a customer's self-service mobile booking,
  when its entire duration fits a specialist's
  discount window and the customer's subscription is active and valid through
  the visit date (inclusive). Missing, paused or expired subscriptions and
  inactive customer accounts pay the full service price.
- Partner bookings identify the customer by normalized phone; mobile bookings
  use the authenticated customer's phone. The client cannot grant a discount.
- Manual bookings made by partners or managers always use the full service
  price, including manual additions to a group, even with an active subscription
  inside a discount window. Subscription status does not itself imply a discount.
- The server stores the booking source and does not accept a source override
  from a request. CRM rescheduling preserves the original source: a mobile
  booking remains eligible subject to the new visit date/window; a manual
  booking never becomes eligible. Legacy bookings have source `unknown`:
  migration preserves their price snapshots, but repricing applies full price.
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

## Booking availability, attendance and service passes

- CRM start-time selectors use
  `GET /api/v1/partner/bookings/availability/` with `date`, `specialist_id`,
  comma-separated `service_ids`, optional `client_phone` and
  `exclude_booking_id` when rescheduling. Slots use a 15-minute step and exclude
  past times, breaks, occupied intervals and full groups. Both ends of the
  requested visit are checked; existing duration snapshots take precedence over
  current service durations. Saving repeats the checks under the partner lock.
- A crown remains on a booking card in promotion hours regardless of its status
  colour. Its tooltip distinguishes promotion hours from an actually applied
  discount; manual bookings still do not receive a subscription discount.
- Attendance is stored in each participant's booking status. Completed
  participants remain checked and read-only when the details are reopened.
- `Service.is_pass` is separate from `is_subscription` (availability through the
  platform subscription). Pass services specify `visit_count` (1–365) and
  `pass_price_mode`: `per_visit` or `total`. Existing services remain non-passes.
- Individual-service CRM enrolment uses `POST /api/v1/partner/bookings/passes/` with a UUID
  `request_id`, `service_id`, `specialist_id`, `client_name`, `client_phone` and
  `visits` (an ISO datetime array). All dates are validated before creating any
  visits. The series is atomic; a retry with the same key and payload returns
  the original visits, while a changed payload returns 409. Dates are sorted
  chronologically before numbering.
- The CRM can generate dates by selected weekdays (weekly if no weekdays are
  selected), then edit each date and available time. Each booking exposes
  `booking_pass`, including its visit number, original visit count, base total
  price, completed count and the linked visits with dates/statuses.
- A total package price is allocated across visits in cents, with the remainder
  allocated to the first visits, so the sum exactly equals the original price.
  Per-visit prices are not divided. Mobile discounts are calculated separately
  for each visit against its date/window/subscription. Changing the service's
  price or visit count never changes existing pass allocations.
- Mobile catalog services expose the pass fields. To book a pass, the existing
  `POST /api/v1/mobile/bookings/` additionally requires `request_id` and `visits`;
  `starts_at` must equal the first visit and every time must match a 30-minute
  slot. The response includes the linked series. Mobile app screens must send
  these fields when enrolling in a pass.
- A pass visit can be moved independently without changing its allocated base
  price or the other dates. Mobile discounts are rechecked on rescheduling.
  Its service and customer phone cannot be replaced. Deleting a pass visit
  cancels it instead of removing its history. No-shows and cancellations remain
  in the series and do not count as completed visits/revenue; they do not create
  automatic replacement visits or refunds.
- The schedule editor supports rectangular date selection by dragging,
  Ctrl/Cmd to add an area, Shift to select a continuous date range, and keyboard
  date selection. Clicking a selected date removes it, including the final
  selected date; with no dates selected, day settings and saving are disabled.
  Saving checks existing bookings, including visits that would
  extend beyond shortened working hours. The editor saves through
  `PATCH /api/v1/partner/specialists/schedule/` with
  `items: [{specialist_id, working_schedule}]`; all selected specialists update
  atomically under the same partner lock as bookings, or none do.
- Dashboard customer search matches partial case-insensitive names and
  formatted/partial phone numbers, combined with the existing filters.

### Independent groups and one-off lesson changes

The CRM **Groups and passes** screen separates the service template, the group,
its dated lessons, and each client's visits. Creating a group does not create
bookings, customers, revenue, or fake participants. Empty lessons remain visible
in the calendar as `0 / capacity` and reserve the specialist's full duration.
Removing the final participant does not delete the lesson or free this time.

- `GET/POST /api/v1/partner/groups/`: list or create a group. Creation requires
  `request_id` (UUID), `name`, `service_id`, `specialist_id`, `capacity`, and
  `sessions` (ISO datetimes). Group pass services require the configured number
  of lessons; non-pass group services can have 1–365 lessons. Creation validates
  every date and commits all lessons atomically. Repeated identical requests
  are idempotent; reusing a key with another payload returns 409.
- `GET /api/v1/partner/groups/{id}/`: lessons, current participants, and client
  visit history, including individually moved or cancelled bookings.
- `GET /api/v1/partner/groups/sessions/`: calendar sessions, including empty and
  cancelled lessons. Specialist, capacity, duration and prices are snapshots of
  the created group rather than guesses from its current participant list.
- `POST /api/v1/partner/groups/{id}/enroll/`: `request_id`, `client_name`,
  `client_phone`, `session_ids`. Dates can be selected individually. Omitting
  `session_ids` selects all future scheduled lessons; the server never silently
  drops full dates. Any capacity, schedule or client conflict rejects the whole
  enrollment. The UI explicitly shows selected dates and their total.
- `PATCH /api/v1/partner/groups/participants/{booking_id}/`: `action` is
  `complete`, `no_show`, `cancel`, or `move`. A move accepts `session_id` for
  another lesson of the same service and duration, or `specialist_id` plus
  `starts_at` for a separate makeup visit. Only this client's selected visit
  changes; original lesson and other visits stay intact. Source history is
  retained, and a makeup visit reserves the full specialist interval.
- `PATCH /api/v1/partner/groups/sessions/{session_id}/`: a deliberately separate
  **whole-lesson** action. `{"action":"move","starts_at":"..."}` changes this
  single dated lesson and all its active participants, not the recurring work
  schedule or any other lesson. For example, moving this Monday from 15:00 to
  16:00 leaves every subsequent Monday at 15:00. The original datetime is
  retained and displayed as a one-off change. The server checks the teacher and
  **every participant** before saving; a single conflict aborts the whole move.
  `{"action":"cancel"}` cancels only this lesson and its active records, releases
  the teacher's time, and preserves history. Separately moved clients are not
  affected. Past lessons and lessons with attendance cannot be changed this way.
- Attendance actions, including the legacy `group_action=complete`, only change
  explicitly selected clients. Unselected clients are never marked absent.
- The group's per-lesson base prices are fixed at creation. A total price is
  divided in cents across the original lesson list; enrollment in selected dates
  costs exactly the sum of those dates, including when joining mid-course.
  Individual/whole-lesson moves preserve allocated base prices. Mobile discounts
  are rechecked for the new date; manual entries stay full-price. Cancellation
  does not automatically generate refunds or replacement visits.
- Availability accepts `reserve_group=1` when reserving a new whole lesson or
  private makeup time, plus `exclude_session_id` when moving an existing lesson.
  Ownership is checked. Empty reservations are also respected by mobile
  availability, legacy booking APIs, schedule edits, service/specialist archival
  and capability removal. The old booking API still supports per-client moves;
  it never moves the underlying group lesson.
- Migrations `0027`–`0029` create the independent records and attach legacy
  group bookings without changing their IDs, client history, prices or statuses.
  Individual passes are unaffected. Old clients creating group bookings or passes
  automatically attach to an existing compatible session or create a stored one.
  Unlinked historical records with unavailable service/specialist references
  retain their legacy representation instead of being discarded.

Run the focused regression suite with a disposable test database:

```bash
python manage.py test partner_api.test_groups partner_api.test_booking_updates partner_api.tests partner_api.test_lifecycle mobile_api.tests --noinput
```

The lifecycle concurrency case requires PostgreSQL; SQLite does not certify
row-lock behaviour. Frontend calendar selection regression tests use the
existing TypeScript dependency and Node's built-in test runner:

```bash
cd frontend/web-partner
node --test tests/booking-controls.test.cjs
```

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
