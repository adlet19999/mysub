# MySub: реализованные обновления Mobile API

Отчёт по требованиям BE-001–BE-014, ноябрь 2026.

## Коротко для мобильного разработчика

Реализована основная серверная часть P0/P1 в существующем Django backend:
единый вход по телефону, защищённые сессии, обновлённый профиль, создание
и перенос записей, ресурсы, отзывы, избранное, уведомления и статистика.
Нового backend или отдельной клиентской базы нет. Flutter-код не изменялся.

**Это отчёт о реально изменённом коде, а не только аудит старых возможностей.**
Обновления не развёрнуты на сервере. Старый `dev.mysub.kz` не является
подтверждением доступности новых методов. Пока код не опубликован и не
развёрнут, проверять его нужно в этой рабочей копии или на подготовленном
разработчиком отдельном тестовом стенде.

Настоящая SMS-интеграция, production HTTPS/CORS, утверждённые документы,
реальный каталог и P2-платежи не подменены демонстрационными результатами.
Это не заявление о закрытии всех BE на100%: внешняя приёмка, коммерческие
условия и юридические решения остаются отдельными зависимостями.
Ниже они явно отделены от готовой серверной части.

## 1. Статусы всех требований

| ID | Результат в коде | Ограничения выпуска |
|---|---|---|
| BE-001 | `verify-code` создаёт нового клиента или авторизует существующего; одноразовые хешированные OTP, срок, попытки, resend, throttling, rotation и logout | Подключить и принять настоящий SMS-провайдер; production доставка не проверена |
| BE-003 | Идентификаторы, длительность/конец, статусная группа, цены-снимки, revision, eligibility, повторяемая отмена и typed pass | Суммы брони не являются подтверждением банковской оплаты; возвраты не реализованы |
| BE-011 | Изоляция аккаунтов, PATCH/revision/дети/аватар, единые ошибки, multipart binary, защищённый OpenAPI; полная регрессия на PostgreSQL | Не проверены production DNS/HTTPS/CORS и native/web медиадоставка |
| BE-006 | Полная история с `total`/`is_complete`; отдельная all-time/month статистика и правила подсчёта визитов | Нет финансового ledger возвратов; суммы основаны на сохранённых данных брони |
| BE-005 | Комментарий/участник/автомобиль, обычные и pass request receipts, quotes, medical/beauty entries, занятия групп, столики, залы/объекты | Объекты только фиксированной длительности; ночёвки и многодневные тарифы не включены |
| BE-004 | Перенос того же booking ID в транзакции, проверка revision/цены/занятости, независимость соседних услуг | PostgreSQL регрессия пройдена локально; production стенд не развёрнут |
| BE-002 | Один отзыв на завершённую принадлежащую клиенту запись, readback, повторы, модерация, public pagination/rating | Публикацию выполняет модератор; нет выдуманных positive/negative секций |
| BE-008 | Account-scoped list, repeat-safe add/remove и atomic clear favorites | Избранное не гарантирует доступность партнёра после его отключения |
| BE-009 | Feed, unread count, read/read-all, настройки, регистрация/ротация push-устройств и transactional outbox с retry | Настоящий push gateway adapter и запуск worker нужно настроить; по умолчанию push выключен |
| BE-010 | Раздельные taxonomy/service-category IDs, коды, реальные рейтинги и связи услуг/специалистов/ресурсов | Нет искусственных районов, distance sort, amenities, verification или production seed данных |
| BE-012 | Backend/CMS для FAQ/legal/support с языком, версией, effective date и публикацией | Владелец должен предоставить 14 утверждённых FAQ и настоящие legal/support материалы |
| BE-013 | OTP-смена номера текущего аккаунта/сессии с сохранением ID и истории | Требуется настоящий SMS-канал; прочие устройства отзываются, текущая сессия сохраняется |
| BE-007 | Чтение существующих admin-managed планов и своей подписки; active/paused/expired/absent согласованы с pricing | Checkout/оплата не включены: нужны платёжный провайдер и утверждённые тарифы/правила entitlement |
| BE-014 | Существующий DELETE сохранён; private receipt подтверждает результат после timeout; legacy ownership tombstones и cleanup аватара | Полная retention/deletion политика не утверждена; UI deletion не объявлен готовым |

## 2. Операции для подключения

Все пути относительно `/api/v1/mobile/`. Для private операций обязателен
`Authorization: Bearer <access_token>`; customer ID из тела не авторизует запрос.
Актуальный контракт генерируется через `schema/`; UI — `docs/`.

| Область | Методы |
|---|---|
| Возможности | GET `config/` |
| Вход | POST `auth/send-code/`, `auth/verify-code/`; legacy new-only `auth/register/` сохранён |
| Сессия | POST `auth/refresh/`, `auth/logout/` |
| Профиль | GET/PATCH/DELETE `users/me/`, POST `users/me/avatar/`, GET `cities/` |
| Смена номера | POST `users/me/phone/request/`, `users/me/phone/confirm/` |
| Каталог | GET `catalog/categories/`, `catalog/partners/`, `catalog/services/` |
| Связи партнёра | GET `catalog/partners/{partner_id}/services/`, `specialists/`, `resources/`, `group-sessions/` |
| Время | GET `catalog/partners/{partner_id}/availability/`; specialist-scoped availability сохранён |
| Записи | GET/POST `bookings/`, POST `bookings/quote/` |
| Восстановление create | GET `bookings/requests/{request_id}/` |
| Изменение записи | POST `bookings/{booking_id}/cancel/`, `reschedule/` |
| Отзыв клиента | GET/POST `bookings/{booking_id}/review/` |
| Публичные отзывы | GET `catalog/partners/{partner_id}/reviews/` |
| Избранное | GET/DELETE `favorites/`, PUT/DELETE `favorites/{partner_id}/` |
| Уведомления | GET `notifications/`, POST `notifications/{notification_id}/read/`, `notifications/read-all/` |
| Настройки уведомлений | GET/PATCH `notifications/preferences/` |
| Push-устройство | PUT/DELETE `notifications/devices/{device_id}/` |
| Подписки | GET `subscriptions/plans/`, `subscriptions/current/` |
| Подтверждение удаления | POST `users/me/deletion-request/`, `auth/deletion-status/` |
| Статистика | GET `bookings/statistics/?month=YYYY-MM` |
| Утверждённый контент | GET `content/?language=ru&kind=legal` |

### Возможности и неподдерживаемые экраны

GET `config/` сообщает currency/timezone, длину и режим OTP, ограничения
профиля/аватара и feature flags. Сейчас `checkout`, `push`,
`resource_nightly_pricing`, `district_filter`, `distance_sort` и
`account_deletion_ui_ready` — false. Не включать соответствующие полные
продуктовые сценарии только из-за наличия нарисованного экрана.

## 3. Авторизация и SMS

1. Передать свой разрешённый тестовый номер в `auth/send-code/`.
2. Дождаться успешного ответа. Ввести полученный код в `auth/verify-code/`.
3. Для нового и существующего клиента ответ HTTP200 одинаковой формы:
   `user`, `tokens.access_token`, `tokens.refresh_token`, `is_new_user`.
4. Не выбирать register через предполагаемый 404. Legacy register оставлен
   только для совместимости: новое создание HTTP201, существующий номер —409.

Телефон нормализуется репозиторным helper в `+7XXXXXXXXXX`, цифры ASCII.
В обычной конфигурации код пятизначный, TTL120 секунд, resend60 секунд,
не более пяти проверок одного challenge. Реальные параметры читать из config;
они конфигурируемы. IP-лимиты: send20/hour, verify60/minute. Перенос IP-limits
между несколькими worker требует общего cache; per-phone задержка и попытки
сохраняются в БД независимо от cache.

Сохраняется хеш, не исходный OTP. Успешный код используется один раз.
Смена режима доставки отзывает ранее созданные challenge. Нет фиктивного
HTTP200 при отсутствующем SMS sender.

Режимы:

- `disabled`: HTTP503 `SMS_NOT_CONFIGURED`.
- `test`: только разрешённый development/test режим, без настоящей SMS;
  ответ явно содержит `delivery_mode=test` и `Development challenge created`.
  Демокод не является production правилом.
- `provider`: `MOBILE_SMS_SENDER` — путь к callable с параметрами
  `phone`, `code`, `expires_in`. Adapter обязан вернуть именно `True`
  **после подтверждения приёма gateway**, либо поднять
  [SMSDeliveryError](./mobile_api/otp.py). `False`/`None` не считаются успехом.
  SDK/API конкретного провайдера не выбран и не подключён.

После refresh сохранять оба новых токена. Старые access/refresh данной
сессии отзываются вместе. На клиенте сериализовать refresh, не отправлять
параллельно несколько запросов обновления одного refresh.
Legacy access без session `jti` требует refresh/повторного входа.

Logout `{}` завершает текущее устройство; `{"all_devices": true}` — все.
Это не DELETE аккаунта. Refresh, signin и mutations используют согласованный
порядок блокировок аккаунта/сессии.

Согласие не устанавливается при входе автоматически. PATCH хранит явно
переданное пользователем согласие/версию; это не доказательство утверждения
документа или его просмотра. До legal approval полноценный consent flow
не объявлен принятой юридической реализацией.

## 4. Профиль и аватар

- `is_profile_complete` сохранён совместимым с опубликованным контрактом:
  **имя + city_id**. Фото/email не делают человека верифицированным.
- Для create сохранён прежний backend minimum — непустое имя. Флаг
  name+city используется для initial-setup routing; это не новая проверка
  личности. Точный возраст Self неизвестен: date_of_birth хранится у детей,
  age bounds проверяются для child, а не выдумываются для взрослого аккаунта.
- PATCH — частичный: пропущенные свойства сохраняются. Пустые `children`
  означают удалить всех детей; отсутствие `children` не изменяет список.
- Новому Flutter передавать актуальный `revision`. Устаревший PATCH →409.
  Без revision сохраняется compatibility last-writer-wins, а не обещание
  защиты от потери соседних изменений.
- Город выбирать из `cities/`; не передавать произвольное название.
  Неизвестный/неактивный city ID отвергается.
- Максимум два ребёнка, только собственные IDs. Имя1–50 Unicode code points:
  буквы, пробел, дефис, обычный/типографский апостроф. Возраст0–17 на текущую
  дату Almaty; рождённый сегодня допустим, будущая дата — нет.
- Для29 февраля календарное сравнение меняет возраст1 марта невисокосного
  года. Это техническое правило, не заявление о юридической норме.
- Для нового детского визита возраст дополнительно проверяется на его дату,
  для pass — на каждую дату. Перенос использует сохранённый attendee snapshot:
  удаление ребёнка из профиля само по себе не удаляет оплаченный/сохранённый
  визит, но новые возрастные ограничения проверяются.

Загрузка — multipart `file`, в OpenAPI это **binary**, не URI.
Точный предел **5,242,880 байт**: равенство допустимо, +1 байт →413.
Декодирование/verify выполняет Pillow; проверены JPEG, PNG, WEBP и GIF.
HEIC/HEIF decoder в текущем interpreter отсутствует: преобразовать на клиенте
в JPEG/PNG, не обещать HEIC поддержку.

Некорректное изображение/слишком большие размеры →400; превышение byte cap
→413; неподдерживаемый HTTP Content-Type/parser →415. Maximum25 млн пикселей,
EXIF orientation учитывается, выходной WEBP ограничен1280×1280.
Это аватар, не оригинал для полноэкранной галереи партнёра.

Upload сразу сохраняет avatar в текущем профиле. При потере ответа проверить
GET `users/me/`, не считать upload/profile PATCH одной атомарной операцией.
Отклонённый PATCH сохраняет старый файл; database failure после новой записи
файла убирает новый orphan. Замена удаляет старый локальный файл после commit.

URL версии содержит UUID; public image response — WEBP/nosniff и immutable
cache. Старые cached копии могут существовать вне backend после локального
удаления: CDN/cache retention требует отдельной политики. Частные ответы —
`Cache-Control: no-store`; общий ETag/offline-контракт не добавлен.

## 5. Создание, цены и восстановление после timeout

Для обычной услуги сохранить request UUID до первого отправления:

```json
{
  "partner_id": 12,
  "service_id": 34,
  "specialist_id": 56,
  "starts_at": "2026-12-03T15:00:00+05:00",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "comment": "Комментарий клиента",
  "attendee": {"type": "self"},
  "expected_final_price": "5000.00"
}
```

**Все IDs, UUID, даты и цены в примерах синтетические.** Для проверки заменить
их реальными связанными объектами своего тестового стенда и его свободным
временем; для нового действия генерировать новый UUID.

POST `bookings/quote/` принимает те же поля одной записи/pass, проверяет
доступность и pricing, но возвращает `is_reserved=false` и не сохраняет бронь.
При create/reschedule доступность и цена проверяются заново.
`expected_final_price` защищает согласованную **итоговую** сумму: изменение
→409 `PRICE_CHANGED`, без частичного сохранения. Это не списание денег.

Обычный create UUID рекомендован; для pass и entries обязателен.
Ключ scoped на account+operation. Первое создание →201, повтор идентичного
нормализованного запроса →200 с текущим authoritative readback. Изменение
набора полей/значений с прежним UUID →409 `REQUEST_CONFLICT`.
Не менять optional поля при повторе после timeout.

GET `bookings/requests/{request_id}/` восстанавливает create после потери
ответа. Если запись неизвестна —404, это не синтетический успешный результат.
Сохранять request payload/UUID между restart; не повторять uncertain create
с новым UUID. Durable receipts остаются в БД, пока существует аккаунт;
автоматический срок удаления не введён.

Время — offset-bearing ISO8601; сервер приводит к Almaty. Horizon365 дней,
начало строго будущее, шаг — `slot_interval_minutes` предложения. Шаг не равен
длительности: например, услуга60 минут может начинаться каждые30.
Не заменять выбранное время timezone устройства.

Service-wide availability для обычных услуг возвращает все допустимые
`allocations` с `specialist_ids` или `resource_ids`, а не случайного мастера.
Для required occurrences группа использует `group-sessions/`, не
несуществующие слоты specialist availability. Выбранный класс передавать
через `group_session_id`, с его teacher/time/duration.

### Категории

- **Салон:** selected eligible specialist обязателен.
- **Медицина/салон, несколько услуг:** корневые `partner_id`, UUID, `entries`
  от1 до10. У каждой строки свои service/specialist/start/comment.
  Строки идут по времени без пересечения, в **одну местную календарную дату**;
  создание all-or-nothing. Нельзя одновременно передать entries и поля одной
  записи. Для quote запросить каждую строку отдельно; согласовать суммарную
  цену. Каждая сохранённая строка имеет собственный booking ID, соседние
  строки доступны в `booking_group.entries` и меняются независимо.
- **Курсы:** реальные scheduled occurrences/teacher/capacity/remaining seats,
  `is_bookable`; неактивный/отвязанный teacher не выдаётся. Разные собственные
  дети могут занимать разные места одновременно. Self/unknown legacy attendee
  не подменяется автоматически ребёнком; unknown legacy overlap консервативен.
- **Ресторан:** `party_size`1–1000, без specialist/resource/vehicle/class.
  Представитель — владелец аккаунта (`self`), гости задаются количеством.
  Сервер выбирает наименьший подходящий свободный стол на120 минут.
  Stable table ID, guest count и `restaurant.table_snapshot` сохраняются;
  legacy snapshot может быть null. `table_name/table_capacity` — текущие
  справочные поля. Перенос обновляет allocation snapshot и hold.
  Existing CRM arrival/renewal/payment completion flow сохраняется.
- **Автомойка:** `vehicle.model`1–120 и `registration_plate`1–32 символа.
  Номер trim/upper; не заявляется проверка юрисдикции. Это snapshot одной
  записи, не отдельный owned garage.
- **Фотостудия/отдых:** `resource_id` принадлежащего залу (`hall`) или объекту
  (`unit`), optional party_size с проверкой capacity. Specialist не выбирается.
  Working schedule и эксклюзивная занятость проверяются. Только individual,
  fixed-duration daytime offers; nightly/multi-day rates не реализованы.

### Абонемент услуги

Используются существующие `is_pass`, `visit_count`, `pass_price_mode` и
`visits`. Все даты резервируются одной транзакцией. Требуются точное число
посещений, UUID, будущие уникальные допустимые даты; starts_at совпадает с
первым отсортированным посещением. Teacher один; selected group pass связан
с реальными sessions той же группы.

`booking_pass` теперь typed: ID, group, visit_number/count, price_mode,
total_price, completed_visits и все visit IDs/status/time/amounts.
В mobile readback выдаются только принадлежащие этому аккаунту visit rows.
При CRM-передаче одного посещения другому клиенту `owned_visit_count`
отражает доступную часть, `is_complete=false`; чужие даты/IDs/status не видны.
`visit_count` и `total_price` остаются исходными количеством и базовой ценой
пакета, а не доказательством текущего owned balance; completed_visits scoped.
При partial ownership остаток не вычислять как original visit_count minus
completed; использовать собственные rows и owned_visit_count.
Для total0.03 на два посещения allocation0.02+0.01, без потери копейки.
Discount rounding — ROUND_HALF_UP. Отмена/перенос одного посещения не отменяет
соседние. Это partner pass, не MySub account-wide paid subscription.

## 6. Readback, отмена и перенос

Бронь содержит stable service/specialist IDs, starts/ends/duration, KZT,
amount strings, status/status_group, revision, comment/attendee/vehicle,
resource/pass/group/review metadata и eligibility.
Не восстанавливать identity по имени. Если legacy identity неоднозначна,
nullable ID/duration не выдумывается; перенос может быть недоступен.
Для table/resource `specialist_id=null`: legacy display name не является
именем настоящего врача/мастера.

Canonical groups: upcoming/completed/cancelled/no_show/unknown.
Неизвестный статус не означает completed или право отмены. Cancel разрешён
только до начала активной брони; уже отменённая →repeat200. Нет обещания
free refund или специального subscription cutoff.

Перенос:

```json
{
  "starts_at": "2026-12-03T16:00:00+05:00",
  "revision": "<актуальная revision из readback>",
  "request_id": "<новый UUID этого переноса>",
  "expected_final_price": "5000.00"
}
```

Меняется тот же booking ID, а не cancel+create. Original slot сохраняется
при conflict/ошибке; target reserve и отпускание original атомарны.
Optional specialist/comment/resource поддерживаются по типу записи.
Revision и UUID обязательны. Повтор того же operation UUID возвращает
текущее состояние; другой payload —409. Stale revision —409 `STALE_BOOKING`.
Для uncertain reschedule повторить тот же payload или перечитать историю;
create-request lookup не является отдельным reschedule lookup.

## 7. История, статистика и остальные account features

GET `bookings/` возвращает **полную** account collection, включая cancelled,
в порядке starts_at DESC, ID DESC; без скрытого50-item limit. `total` —
число записей, `is_complete=true`. Genuine empty account —200 с пустым data;
ошибка/401 не превращается в успешную пустоту.

Статистика `bookings/statistics/?month=YYYY-MM`:

- explicit completed aliases, не вычисление completed из прошедшей даты;
- Almaty starts_at, полуоткрытая граница первого дня месяца/следующего;
- pass visits и участники классов считаются отдельными завершёнными визитами;
- medical/beauty batch — один visit, completed_entries — число завершённых
  строк; при partial completion суммы берутся только с completed строк;
- savings — сохранённые discount_amount завершённых строк, cancelled/no-show
  не входят; отрицательные stored amounts →409, не скрытый ноль;
- final_price_total — сумма сохранённых цен, не банковский payment ledger
  и не обязательно ресторанный paid_amount; refunds не интерпретируются.

Money — десятичные строки в основных единицах KZT, не копейки и не binary float.
Monthly/lifetime totals не вычислять из страницы reviews/notifications.

Отзыв: rating1–5, optional comment до2000 Unicode code points. Один на owned
completed booking. Identical repeat →200, изменённый →409. State pending,
published или hidden; private readback сохраняет статус после restart.
Публично только published, anonymous author display, без customer/booking IDs.
Pagination limit1–100, order newest/oldest, optional language ru/kk/en,
opaque next_cursor. `rating/rating_count` глобальные, `total` — отфильтрованный.

Favorites: повтор PUT/DELETE безопасен; DELETE collection очищает всё.
Notifications: такой же opaque cursor/order/limit, unread_count/total,
repeat-safe read/read-all; preferences не скрывают in-app feed.
Типы booking.created/booking.changed и параметры назначения не авторизуют
операции с чужой записью. In-app feed не зависит от включения push.

### Push: устройство, очередь и доставка

PUT `notifications/devices/{device_id}/`: installation UUID, `platform`
android/ios/web и `token` до4096 ASCII characters без whitespace. Ответ200
возвращает id/platform/is_active/updated_at, но не token. Повтор с тем же
UUID ротирует token. Чужой UUID с другим token —409; повторное использование
одного token под другим UUID —409. При account switch тот же installation
UUID+token можно перепривязать новому authenticated account. Старые queued
events после перепривязки не отправляются.

DELETE unregister идемпотентен и ограничен current account+session.
Refresh переносит registration на новую session; logout/current/all-devices
отключает соответствующие devices. Смена телефона отключает устройства
отозванных sessions, текущее сохраняет. Удаление аккаунта удаляет устройства
и их delivery records.

`MOBILE_PUSH_SENDER` — import path реального gateway adapter. По умолчанию
пустой: config.features.push=false, registration возвращает503
`PUSH_NOT_CONFIGURED`. Наличие import path не является проверкой доставки.
Adapter callable принимает keyword arguments `token`, `platform`, `data`,
`delivery_id`; возвращает строгоTrue после gateway acknowledgement.
Temporary failure: `PushDeliveryError`; permanent rejected token:
`PushTokenInvalid`. Adapter обязан ограничивать сетевой timeout.

Notification и outbox создаются в одной транзакции. Worker:
`python manage.py send_mobile_push --limit 100`, limit1–1000; запускать
регулярно планировщиком или с `--watch` (пауза10 секунд между batch).
В production Compose worker доступен в optional profile `push`; включать
только после настройки настоящего adapter:
`docker compose -f docker-compose.prod.yml --env-file .env.prod --profile push up -d --build`.
PostgreSQL workers используют SKIP LOCKED.
До отправки повторно проверяются owner, session expiry/revocation и
preferences. Отправляется только `data={"type":"inbox.updated"}`: без
имени, телефона, booking ID и private URL. После push приложение загружает
inbox с текущей авторизацией.

Gateway failures логируются без token/exception body; до5 попыток,
backoff2/4/8/16 минут, затем failed. Invalid token отключает устройство.
Это at-least-once доставка: adapter должен использовать delivery_id для
deduplication, если gateway это поддерживает. Gateway acknowledgement не
доказывает получение устройством. Неожиданные ошибки adapter не скрываются.

### Подписка: только существующие данные, без фиктивной оплаты

GET `subscriptions/plans/` публикует реальные неархивные admin-managed
планы: id/name/monthly_price/duration_months/description, KZT, complete.
Monthly price не превращается в выдуманную стоимость checkout:
`price_is_checkout_quote=false`, `checkout_available=false`.

GET `subscriptions/current/` требует Bearer и возвращает только свою
подписку: id/plan_name/status/is_active/expires_on/time_zone.
Status absent/active/paused/expired. Дата expires_on включительна,
null означает отсутствие указанной даты окончания; source=admin_assigned.
Для будущей брони subscription дополнительно должна покрывать дату визита;
`quote_required=true`. Название подписки не используется как plan ID.
Клиент не может активировать подписку через эти read-only методы.

### Удаление: подтверждение результата после потери ответа

1. Авторизованный POST `users/me/deletion-request/` без тела возвращает201
   с private `receipt`, expires_at и state=requested. Аккаунт не удаляется.
2. Сохранить receipt защищённо. DELETE `users/me/` может передать его
   в заголовке `X-Deletion-Receipt`. Чужой/expired/другой session receipt
   даёт409 без удаления. Refresh переносит подготовленный receipt.
3. После204 либо timeout выполнить POST `auth/deletion-status/` с
   `{"receipt":"<сохранённый receipt>"}`. Bearer не требуется: после
   удаления он уже отозван. Возвращаются только state=requested/deleted,
   completed_at и expires_at. Invalid/expired receipt —404; неизвестный
   результат не подменяется словом deleted.

Receipt secret хранится только как SHA256, живёт7 дней и не содержит
телефон, customer ID или JWT. POST/status имеют throttle30/hour per IP
и Cache-Control:no-store. Не передавать receipt в URL или аналитику.
`purge_mobile_deletion_receipts` удаляет только истёкшие receipts.
Подготовленные receipts подтверждаются и при legacy DELETE без заголовка.
Completion сохраняется атомарно с удалением; rollback не подтверждает успех.
Перед удалением legacy bookings привязываются к ownership tombstones:
повторная регистрация номера не получает историю прежнего владельца.

Это дополняет существующий DELETE, но не утверждает юридическую retention
политику. DELETE удаляет user/profile/children/sessions/favorites/notifications/
push registrations/локальный avatar; booking snapshots и анонимизированные
ownership references сохраняются. Review customer становитсяnull.
Не обещать автоматическую отмену будущих записей, возвраты или стирание
всех CRM snapshots. config.features.account_deletion_ui_ready остаётсяfalse.

Смена телефона: authenticated request и confirm для proposed number,
challenge bound к account+current session. Чужой занятый номер —409.
ID/children/subscriptions/bookings сохраняются, другие sessions отзываются,
текущая остаётся для readback после timeout. Повтор confirm уже установленного
номера →200 changed=false. Phone PATCH не поддерживается.

## 8. Каталог и контент

`category_id` — общий BusinessCategory ID или null; `service_category_id` —
отдельный tenant service-category ID. Не сравнивать два пространства IDs.
Known booking codes: restaurant, beauty, medical, carwash, photo_studio,
recreation, courses. Broad/unknown shortcut не получает выдуманный код:
например, автоуслуги не обязательно автомойка.

Mixed service category и primary category учитываются через существующую
group policy и booking metadata. Использовать booking_mode/requires_occurrence
и фактические связи, не выводить eligibility из названия или фото.
Ratings — только опубликованные reviews; отсутствие рейтинга null/count0,
не фиктивные5 звёзд. District/distance/verification/amenities не изобретены.

Ресурсы и CMS заполняются штатным Django admin; resource связывается со своим
партнёром/услугами, working schedule/capacity должны быть реальными.
GET resources выдаёт active public associations, не IDs private tenant услуг.
Контент публиковать с корректными language/version/effective_at, publication,
body или owned HTTPS legal URL. Пока rows не утверждены и не доступны,
content возвращает data=[] и `is_configured=false`, а не образцы поддержки.
Viewing legal body не записывает consent.

## 9. Ошибки для Flutter

Управляемые validation/auth/conflict/rate errors:

```json
{
  "error": {
    "code": "STALE_BOOKING",
    "message": "Запись изменилась; перечитайте её",
    "details": [{"field": "revision", "message": "Перечитайте запись"}]
  }
}
```

Основные группы:400/422 input/profile limits,401 revoked/invalid session,
404 unknown/unowned entity,409 conflict/price/revision,413 avatar byte cap,
415 parser,429 resend/attempt/IP limit,503 SMS unavailable.
401 имеет `WWW-Authenticate: Bearer`; retry hints — `Retry-After`
и optional error.retry_after. Unhandled server/framework failures не
гарантируются в этом JSON envelope: не показывать их как успешные данные.

При409 перечитать authoritative booking/profile/quote; не создавать другую
запись или списание автоматически. Чужая сущность не возвращается через
request UUID, review или cancel/reschedule.

## 10. Как проверить

Из корня checkout в PowerShell, с уже существующим backend interpreter:

```powershell
Set-Location .\backend
& .\.venv\Scripts\python.exe manage.py test mobile_api --settings=config.test_settings --noinput
& .\.venv\Scripts\python.exe manage.py test --settings=config.test_settings --noinput
& .\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run --settings=config.test_settings
```

В другой OS/interpreter использовать тот же manage.py с выбранным `python`.
[test_settings.py](./config/test_settings.py) не читает environment files,
использует одноразовую in-memory SQLite DB, отдельные случайные test secrets,
test OTP и locmem email. Реальные аккаунты/SMS/mail не используются.
Не запускать tests на production DB.

**Фактически выполнено:**

- Финальная backend регрессия на отдельном PostgreSQL16:246 tests,246 passed,
  без skipped,187.518s. Одноразовый Docker container удалён после проверки.
- Предыдущая SQLite регрессия до двух последних restaurant/worker тестов:
  244 tests,240 passed,4 PostgreSQL-only concurrency cases skipped,174.983s.
- Frontend regression:34 tests passed; TypeScript `tsc --noEmit` passed.
- Production Compose structural validation passed без чтения environment files;
  новые OTP/JWT/push параметры передаются backend и worker через общий environment.
- Проверены последние mobile изменения:language validation, no-store токенов,
  ownership вложенных pass visits, schema200 repeat/default errors, bookable
  flags, push lifecycle/worker/retries, subscription readback и deletion receipts.
- Django system check:0 issues.
- Migration drift:No changes detected.
- OpenAPI проходит structural validation; multipart binary, typed pass,
  private Bearer security и error references проверяются тестом.
- Pillow runtime check:JPEG/PNG/WEBP/GIF decoder доступны, HEIC/HEIF — нет.

SQLite не сертифицирует PostgreSQL locks. На PostgreSQL выполнены race tests:
[test_concurrency.py](./mobile_api/test_concurrency.py); existing CRM case —
[test_lifecycle.py](./partner_api/test_lifecycle.py). Проверены competing last seat,
identical create replay, CRM last place и два push workers на один delivery.
Также исправлены PostgreSQL nullable-join locks в restaurant actions/renewals
и review ownership query. Наличие локального прогона не заменяет production
приёмку реальных интеграций.

Для повторения на отдельном локальном PostgreSQL используйте
[postgres_test_settings.py](./config/postgres_test_settings.py):
имя исходной DB `mysub_acceptance`, пользователь `mysub_test`, host строго
127.0.0.1. Аккаунт должен иметь право создавать test DB
`test_mysub_acceptance`. Пароль передаётся только process environment через
`MYSUB_TEST_PG_PASSWORD`, порт — `MYSUB_TEST_PG_PORT`. При отсутствии пароля
settings явно отказывают в запуске. Они не читают environment files.

После подготовки **одноразового** PostgreSQL:

```powershell
& .\.venv\Scripts\python.exe manage.py test --settings=config.postgres_test_settings --noinput
```

Это настройки только для tests, не для web server, миграций рабочей базы
или подключения к production. Не использовать ключи/данные рабочего сервиса.

### Сценарии ручной приёмки на отдельном стенде

1. Применить новые migrations0004–0007; заполнить настоящие связи каталога,
   расписания, классы, залы/объекты/столики. Test numbers согласовать отдельно.
2. Signin новый/существующий; wrong/expired/reused code, resend, logout,
   refresh старого токена и попытки другого аккаунта.
3. PATCH с актуальной/stale revision; omission vs children=[]; свои/чужие
   child IDs, день18-летия, valid/invalid city.
4. JPEG/PNG upload; ровно5,242,880/+1 bytes, invalid input, GET image и profile;
   failed PATCH сохраняет старый avatar. Проверить реальный native/web renderer.
5. Quote без записи →create201 →same request200 →changed request409;
   lost response восстановить request lookup. Проверить исходный slot.
6. Ресторан2-hour allocation/guest count/snapshot; hall capacity;
   два ребёнка в классе и отказ на третье место; carwash vehicle.
7. Two-entry medical visit, failure второй строки откатывает все записи;
   независимый cancel/move и отказ разных календарных дат.
8. Pass total0.03/2 visits →0.02+0.01, rollback на недоступной дате,
   отмена одной даты сохраняет соседнюю.
9. Completed review pending не виден public, published виден; повтор/
   conflict, global aggregate vs language-filtered page.
10. Favorites clear/repeats, notification read/read-all/preferences,
    exact completed/savings month boundary и verified phone change.
11. Проверить CORS/preflight/API/media hosts и HTTPS; заполнить только
    утверждённые FAQ/legal/support. Не включать false feature flags.
12. Настроить настоящий push adapter, зарегистрировать device, создать
    notification, запустить worker и проверить доставку на телефоне.
    Повторить после refresh/logout/account switch и при выключенных preferences.
13. Проверить subscription absent/paused/expired/inclusive expiry; не
    трактовать admin-assigned subscription как подтверждённую банковскую оплату.
14. Только на disposable account: подготовить deletion receipt, выполнить
    DELETE и повторно прочитать state без JWT. Убедиться, что failed DELETE
    не даёт deleted и повторная регистрация номера не получает прежнюю историю.

### Обновление сервера позднее

Здесь deployment не выполнялся. Следующая команда **сама по себе не публикует
локальные изменения**: использовать её только после разрешённой публикации
этого кода в GitHub и получения доступа к серверу:

```bash
cd /opt/apps/mysub
git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

Production environment file остаётся управляемым владельцем. Проверить
применение migrations и выполнить внешнюю приёмку; эта работа не объявляет
развёрнутый сервер или оплату/SMS production-ready.

## 11. Где находится реализация

- [views.py](./mobile_api/views.py):auth/profile/booking/quote/avatar.
- [account_views.py](./mobile_api/account_views.py):reschedule/reviews/favorites/
  statistics/notifications/phone/content.
- [otp.py](./mobile_api/otp.py):OTP/SMS adapter contract.
- [release_views.py](./mobile_api/release_views.py):push registration,
  subscription readback и deletion receipts.
- [push.py](./mobile_api/push.py):transactional outbox/gateway retry contract;
  [worker command](./mobile_api/management/commands/send_mobile_push.py).
- [booking_contract.py](./mobile_api/booking_contract.py):status/identity/
  revision/ownership/notifications synchronization.
- [catalog_contract.py](./mobile_api/catalog_contract.py),
  [catalog_views.py](./mobile_api/catalog_views.py):category/resource/class/
  availability/config/request lookup.
- [models.py](./mobile_api/models.py), [admin.py](./mobile_api/admin.py),
  [migrations](./mobile_api/migrations):durable data и management surfaces.
- [serializers.py](./mobile_api/serializers.py), [schema.py](./mobile_api/schema.py):
  typed OpenAPI и protected/error contract.
- [test_updates.py](./mobile_api/test_updates.py):acceptance regressions.
- [test_release.py](./mobile_api/test_release.py):push/subscription/deletion
  acceptance и OpenAPI новых endpoints.
- [partner pricing/overlap helpers](./partner_api/views.py) и
  [group helpers](./partner_api/group_views.py):shared CRM/mobile consistency.

## 12. Внешние зависимости: что ещё нужно для полного запуска

На04.11.2026 technical acceptance локального кода выполнена, но полный
production release всех BE не объявляется завершённым. Названия реальных
провайдеров и условия были запрошены; ответа пока нет. Без них нельзя
выбрать платёжную интеграцию или заявить доставку SMS/push.

| Зависимость | Ответственный и необходимый результат |
|---|---|
| SMS | Владелец/мобильный разработчик: действующий provider, API docs, согласованные test numbers; секреты настраивает владелец, затем проверяется реальная доставка |
| Push | Мобильный разработчик: provider/project/platform configuration; backend gateway adapter и расписание worker, затем приёмка на настоящем устройстве |
| Оплата/планы | Владелец: провайдер, утверждённые цены/периоды/benefits/refund/renewal policy; checkout не включать до verified payment acceptance |
| Ночёвки/многодневные объекты | Владелец: входят ли в релиз, реальный inventory, check-in/out, nightly/period тарифы, occupancy/отмена; пока только fixed-duration resource booking |
| FAQ/legal/support | Владелец:14 утверждённых ответов, документы/версии/языки, реальные owned contacts |
| Удаление | Владелец: retention/anonymization policy, судьба будущих записей, отзывов, платежей и восстановление; receipt не подменяет это решение |
| Production acceptance | Администратор и мобильный разработчик: разрешённая публикация/стенд, HTTPS/DNS/CORS/media и native/web сценарии |

Ранее пакет сохранялся только локально. После запроса04.11.2026 команды
обновления сервера весь проверенный пакет подготовлен к публикации в GitHub,
чтобы git pull мог получить изменения. Сам deployment здесь не выполнялся.
Environment files, посторонние изображения и документы не изменялись.

## 13. Исправление ошибки ресторанных действий

Ошибка `Unexpected token '<' ... is not valid JSON` воспроизведена на
HTML500 response: интерфейс безусловно вызывал response.json().
На PostgreSQL также воспроизведена серверная причина restaurant500:
FOR UPDATE затрагивал nullable table join. Restaurant actions и renewals
теперь блокируют только Booking row через `of=("self",)` под partner lock.

В CRM столиках, сохранении/действиях брони и загрузке свободного времени
используется общий parser, который сохраняет JSON business errors, а для
HTML/пустого/некорректного ответа показывает понятный текст с HTTP status.
HTML body не выводится пользователю. Некорректный успешный ответ не
принимается за сохранённую бронь/столик.

Добавлены frontend regressions для HTML404/500/502/503, malformed/empty200,
JSON409,204 и network read failure, а также PostgreSQL API test на JSON
ответы списка/редактирования/архивирования столиков и действий с бронью.
На стенде после обновления проверить перенос, приход, отмену/неявку и
завершение с оплатой. Если upstream всё же недоступен, интерфейс покажет
HTTP status вместо JS SyntaxError — это не подмена серверного сбоя успехом.
