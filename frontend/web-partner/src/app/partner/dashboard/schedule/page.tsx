"use client";

import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type WorkingDayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

type WorkingDaySchedule = {
  day: WorkingDayKey;
  is_day_off: boolean;
  start_time: string;
  end_time: string;
  break_start: string;
  break_end: string;
};

type Specialist = {
  id: number;
  full_name: string;
  description?: string;
  working_schedule: WorkingDaySchedule[];
  service_kind_ids?: number[];
  is_active: boolean;
};

type Service = {
  id: number;
  name: string;
  kind: number | null;
  kind_name?: string | null;
  duration_minutes?: number;
  price: string | null;
  is_active: boolean;
};

type BookingLine = {
  id: number;
  serviceId: string;
  sum: string;
};

type Booking = {
  id: number;
  service_name: string;
  manager_name: string | null;
  starts_at: string;
  client_name: string;
  client_phone: string;
  status: string;
};

type BookingStatusTone = "success" | "warning" | "danger" | "muted";

type CalendarBooking = {
  booking: Booking;
  minutes: number;
  durationMinutes: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

const RUS_WEEKDAY: Record<WorkingDayKey, string> = {
  mon: "понедельник",
  tue: "вторник",
  wed: "среда",
  thu: "четверг",
  fri: "пятница",
  sat: "суббота",
  sun: "воскресенье",
};
const RUS_MONTH: string[] = [
  "января",
  "февраля",
  "марта",
  "апреля",
  "мая",
  "июня",
  "июля",
  "августа",
  "сентября",
  "октября",
  "ноября",
  "декабря",
];

const HOURS = Array.from({ length: 12 }, (_, index) => 9 + index);

function toWorkingDayKey(date: Date): WorkingDayKey {
  const day = date.getDay();
  if (day === 0) return "sun";
  if (day === 1) return "mon";
  if (day === 2) return "tue";
  if (day === 3) return "wed";
  if (day === 4) return "thu";
  if (day === 5) return "fri";
  return "sat";
}

function formatDateTitle(date: Date) {
  return `${date.getDate()} ${RUS_MONTH[date.getMonth()]} ${date.getFullYear()}`;
}

function formatDateInputValue(date: Date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function parseBookingDateTime(raw: string) {
  const directMatch = raw.match(/^(\d{4}-\d{2}-\d{2})[T\s](\d{2}):(\d{2})/);
  if (directMatch) {
    return {
      dateKey: directMatch[1],
      hour: Number(directMatch[2]),
      minutes: Number(directMatch[3]),
      timeLabel: `${directMatch[2]}:${directMatch[3]}`,
    };
  }

  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) {
    return null;
  }

  const dateKey = formatDateInputValue(date);
  const hour = date.getHours();
  const minutes = date.getMinutes();
  return {
    dateKey,
    hour,
    minutes,
    timeLabel: `${String(hour).padStart(2, "0")}:${String(minutes).padStart(2, "0")}`,
  };
}

function parseServiceNames(raw: string): string[] {
  return raw
    .split(/\r?\n/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function getStatusTone(status: string): BookingStatusTone {
  const normalized = status.trim().toLowerCase();
  if (["completed", "done", "завершен", "завершена"].includes(normalized)) {
    return "success";
  }
  if (["booked", "pending", "записан", "записана"].includes(normalized)) {
    return "warning";
  }
  if (["no_show", "no-show", "missed", "неявка"].includes(normalized)) {
    return "danger";
  }
  if (["cancelled", "canceled", "отменен", "отменена"].includes(normalized)) {
    return "muted";
  }
  return "warning";
}

function getStatusLabel(status: string): string {
  const normalized = status.trim().toLowerCase();
  if (["completed", "done", "завершен", "завершена"].includes(normalized)) {
    return "Завершен";
  }
  if (["booked", "pending", "записан", "записана"].includes(normalized)) {
    return "Записан";
  }
  if (["no_show", "no-show", "missed", "неявка"].includes(normalized)) {
    return "Неявка";
  }
  if (["cancelled", "canceled", "отменен", "отменена"].includes(normalized)) {
    return "Отменен";
  }
  return status || "Записан";
}

export default function SchedulePage() {
  const tenant = TENANT_DEFAULT;
  const [partnerEmail, setPartnerEmail] = useState("");
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [selectedDate, setSelectedDate] = useState<Date>(new Date());
  const [isBookingModalOpen, setIsBookingModalOpen] = useState(false);
  const [bookingModalMode, setBookingModalMode] = useState<"create" | "edit">("create");
  const [editingBookingId, setEditingBookingId] = useState<number | null>(null);
  const [bookingClientName, setBookingClientName] = useState("");
  const [bookingPhone, setBookingPhone] = useState("");
  const [bookingSpecialistId, setBookingSpecialistId] = useState("");
  const [bookingDate, setBookingDate] = useState(formatDateInputValue(new Date()));
  const [bookingStartTime, setBookingStartTime] = useState("16:40");
  const [bookingLines, setBookingLines] = useState<BookingLine[]>([{ id: 1, serviceId: "", sum: "" }]);
  const [modalError, setModalError] = useState("");
  const [isSubmittingBooking, setIsSubmittingBooking] = useState(false);

  const activeSpecialists = useMemo(
    () => specialists.filter((specialist) => specialist.is_active).sort((a, b) => a.full_name.localeCompare(b.full_name)),
    [specialists],
  );

  const selectedDay = toWorkingDayKey(selectedDate);

  const activeServices = useMemo(() => {
    return services.filter((service) => service.is_active).sort((a, b) => a.name.localeCompare(b.name));
  }, [services]);

  const bookableServices = useMemo(() => {
    return activeServices.filter((service) => service.kind != null);
  }, [activeServices]);

  const primarySelectedService = useMemo(() => {
    const primaryLine = bookingLines.find((line) => line.serviceId);
    if (!primaryLine) {
      return null;
    }
    return bookableServices.find((service) => String(service.id) === primaryLine.serviceId) ?? null;
  }, [bookingLines, bookableServices]);

  const selectedServicesInModal = useMemo(() => {
    return bookingLines
      .map((line) => bookableServices.find((service) => String(service.id) === line.serviceId) ?? null)
      .filter((item): item is Service => Boolean(item));
  }, [bookingLines, bookableServices]);

  const availableSpecialistsForService = useMemo(() => {
    const selectedKinds = Array.from(
      new Set(selectedServicesInModal.map((service) => service.kind).filter((kind): kind is number => kind != null)),
    );

    if (!selectedKinds.length) {
      return activeSpecialists;
    }
    return activeSpecialists.filter((specialist) => {
      const capabilities = specialist.service_kind_ids ?? [];
      return selectedKinds.every((kindId) => capabilities.includes(kindId));
    });
  }, [activeSpecialists, selectedServicesInModal]);

  const canSubmitBooking = useMemo(() => {
    if (!bookingClientName.trim() || !bookingPhone.trim() || !bookingDate || !bookingStartTime || !bookingSpecialistId) {
      return false;
    }
    return bookingLines.some((line) => line.serviceId);
  }, [bookingClientName, bookingPhone, bookingDate, bookingStartTime, bookingSpecialistId, bookingLines]);

  const bookingsBySlot = useMemo(() => {
    const map = new Map<string, CalendarBooking[]>();
    const selectedDateKey = formatDateInputValue(selectedDate);
    const serviceDurationByName = new Map<string, number>();
    for (const service of services) {
      const duration = typeof service.duration_minutes === "number" && service.duration_minutes > 0 ? service.duration_minutes : 60;
      const byName = service.name.trim().toLowerCase();
      if (byName) {
        const prev = serviceDurationByName.get(byName);
        serviceDurationByName.set(byName, prev == null ? duration : Math.min(prev, duration));
      }
      const byKindName = (service.kind_name || "").trim().toLowerCase();
      if (byKindName) {
        const prev = serviceDurationByName.get(byKindName);
        serviceDurationByName.set(byKindName, prev == null ? duration : Math.min(prev, duration));
      }
    }
    const specialistIdByName = new Map<number, string>();
    for (const specialist of activeSpecialists) {
      specialistIdByName.set(specialist.id, specialist.full_name.trim().toLowerCase());
    }

    for (const booking of bookings) {
      const parsedStartsAt = parseBookingDateTime(booking.starts_at);
      if (!parsedStartsAt) {
        continue;
      }
      if (parsedStartsAt.dateKey !== selectedDateKey) {
        continue;
      }

      const bookingManagerName = (booking.manager_name || "").trim().toLowerCase();
      const specialist = activeSpecialists.find((item) => specialistIdByName.get(item.id) === bookingManagerName);
      if (!specialist) {
        continue;
      }
      const slotOwner = String(specialist.id);

      const hour = parsedStartsAt.hour;
      const minutes = parsedStartsAt.minutes;
      if (!HOURS.includes(hour)) {
        continue;
      }

      const key = `${hour}-${slotOwner}`;
      const list = map.get(key) ?? [];
      const listedNames = parseServiceNames(booking.service_name);
      const durationMinutes = listedNames.length
        ? listedNames.reduce((sum, name) => sum + (serviceDurationByName.get(name.toLowerCase()) ?? 60), 0)
        : serviceDurationByName.get(booking.service_name.trim().toLowerCase()) ?? 60;
      list.push({ booking, minutes, durationMinutes });
      map.set(key, list);
    }

    return map;
  }, [bookings, selectedDate, activeSpecialists]);

  function formatBookingTime(value: string) {
    const parsed = parseBookingDateTime(value);
    return parsed?.timeLabel ?? "--:--";
  }

  function addMinutesToTimeLabel(startTimeRaw: string, minutesToAdd: number) {
    const parsed = parseBookingDateTime(startTimeRaw);
    if (!parsed) {
      return "--:--";
    }
    const total = parsed.hour * 60 + parsed.minutes + minutesToAdd;
    const safe = ((total % (24 * 60)) + 24 * 60) % (24 * 60);
    const h = Math.floor(safe / 60);
    const m = safe % 60;
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as { email?: string; username?: string };
      const email = (parsed.email || parsed.username || "").trim().toLowerCase();
      if (email) {
        setPartnerEmail(email);
      }
    } catch {
      // ignore invalid localStorage payload
    }
  }, []);

  async function loadDirectory() {
    if (!partnerEmail) {
      return;
    }

    try {
      const headers = {
        "Content-Type": "application/json",
        "X-Tenant": tenant,
        "X-Partner-Email": partnerEmail,
      };
      const [specialistsResponse, servicesResponse, bookingsResponse] = await Promise.all([
        fetch(`${API_BASE}/partner/specialists/`, {
          headers,
          cache: "no-store",
        }),
        fetch(`${API_BASE}/partner/services/`, {
          headers,
          cache: "no-store",
        }),
        fetch("/api/partner/bookings/", {
          headers: {
            "X-Partner-Email": partnerEmail,
          },
          cache: "no-store",
        }),
      ]);

      if (!specialistsResponse.ok) {
        setSpecialists([]);
      } else {
        const specialistsPayload = (await specialistsResponse.json()) as Specialist[];
        setSpecialists(Array.isArray(specialistsPayload) ? specialistsPayload : []);
      }

      if (!servicesResponse.ok) {
        setServices([]);
      } else {
        const servicesPayload = (await servicesResponse.json()) as Service[];
        setServices(Array.isArray(servicesPayload) ? servicesPayload : []);
      }

      if (!bookingsResponse.ok) {
        setBookings([]);
      } else {
        const bookingsPayload = (await bookingsResponse.json()) as { items?: Booking[] };
        setBookings(Array.isArray(bookingsPayload?.items) ? bookingsPayload.items : []);
      }
    } catch {
      setSpecialists([]);
      setServices([]);
      setBookings([]);
    }
  }

  useEffect(() => {
    void loadDirectory();
  }, [partnerEmail, tenant]);

  function openBookingModal() {
    const firstSpecialist = activeSpecialists[0];
    setBookingClientName("");
    setBookingPhone("");
    setBookingSpecialistId(firstSpecialist ? String(firstSpecialist.id) : "");
    setBookingDate(formatDateInputValue(selectedDate));
    setBookingStartTime("16:40");
    setBookingLines([{ id: Date.now(), serviceId: "", sum: "" }]);
    setModalError("");
    setIsSubmittingBooking(false);
    setBookingModalMode("create");
    setEditingBookingId(null);
    setIsBookingModalOpen(true);
  }

  function openEditBookingModal(target: Booking) {
    const startsAt = parseBookingDateTime(target.starts_at);
    const listedNames = parseServiceNames(target.service_name);
    const matchedServices = listedNames
      .map((listedName) =>
        bookableServices.find(
          (item) =>
            item.name.trim().toLowerCase() === listedName.toLowerCase() ||
            (item.kind_name || "").trim().toLowerCase() === listedName.toLowerCase(),
        ) ?? null,
      )
      .filter((item): item is Service => Boolean(item));
    const matchedSpecialist = activeSpecialists.find(
      (item) => item.full_name.trim().toLowerCase() === (target.manager_name || "").trim().toLowerCase(),
    );

    setBookingClientName(target.client_name || "");
    setBookingPhone(target.client_phone || "");
    setBookingSpecialistId(matchedSpecialist ? String(matchedSpecialist.id) : "");
    setBookingDate(startsAt?.dateKey ?? formatDateInputValue(selectedDate));
    setBookingStartTime(startsAt?.timeLabel ?? "10:00");
    setBookingLines(
      matchedServices.length
        ? matchedServices.map((service, index) => ({
            id: Date.now() + index,
            serviceId: String(service.id),
            sum: service.price ? String(service.price) : "",
          }))
        : [{ id: Date.now(), serviceId: "", sum: "" }],
    );
    setModalError("");
    setIsSubmittingBooking(false);
    setBookingModalMode("edit");
    setEditingBookingId(target.id);
    setIsBookingModalOpen(true);
  }

  function closeBookingModal() {
    if (isSubmittingBooking) {
      return;
    }
    setIsBookingModalOpen(false);
  }

  function onServiceChange(lineId: number, serviceId: string) {
    const selectedService = bookableServices.find((item) => String(item.id) === serviceId);
    setBookingLines((prev) =>
      prev.map((line) => {
        if (line.id !== lineId) {
          return line;
        }
        return {
          ...line,
          serviceId,
          sum: selectedService?.price ? String(selectedService.price) : line.sum,
        };
      }),
    );

    if (!selectedService || selectedService.kind == null) {
      return;
    }

    setBookingSpecialistId((prev) => {
      if (!prev) {
        return prev;
      }
      const currentSpecialist = activeSpecialists.find((item) => String(item.id) === prev);
      if (!currentSpecialist) {
        return "";
      }
      const canProvideService = (currentSpecialist.service_kind_ids ?? []).includes(selectedService.kind as number);
      return canProvideService ? prev : "";
    });
  }

  function onSumChange(lineId: number, value: string) {
    setBookingLines((prev) => prev.map((line) => (line.id === lineId ? { ...line, sum: value } : line)));
  }

  function addBookingLine() {
    setBookingLines((prev) => [...prev, { id: Date.now() + prev.length, serviceId: "", sum: "" }]);
  }

  async function submitBooking(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setModalError("");

    const selectedServices = bookingLines
      .map((line) => bookableServices.find((item) => String(item.id) === line.serviceId) ?? null)
      .filter((item): item is Service => Boolean(item));

    const specialist = activeSpecialists.find((item) => String(item.id) === bookingSpecialistId);

    if (!selectedServices.length || !specialist) {
      setModalError("Заполните обязательные поля записи");
      return;
    }

    const requiredKinds = Array.from(
      new Set(selectedServices.map((service) => service.kind).filter((kind): kind is number => kind != null)),
    );

    if (requiredKinds.some((kindId) => !(specialist.service_kind_ids ?? []).includes(kindId))) {
      setModalError("Выбранный специалист не оказывает эту услугу");
      return;
    }

    if (!partnerEmail) {
      setModalError("Не удалось определить партнера");
      return;
    }

    setIsSubmittingBooking(true);
    try {
      const startsAt = `${bookingDate}T${bookingStartTime}:00`;
      const isEditMode = bookingModalMode === "edit" && editingBookingId != null;
      const compositeServiceName = selectedServices
        .map((service) => (service.kind_name || service.name).trim())
        .filter(Boolean)
        .join("\n");
      const response = await fetch(isEditMode ? `/api/partner/bookings/${editingBookingId}/` : "/api/partner/bookings/", {
        method: isEditMode ? "PATCH" : "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Partner-Email": partnerEmail,
        },
        body: JSON.stringify({
          specialist: specialist.full_name,
          service: compositeServiceName,
          clientName: bookingClientName.trim(),
          clientPhone: bookingPhone.trim(),
          startTime: startsAt,
        }),
      });

      if (!response.ok) {
        let message = "Не удалось добавить запись";
        try {
          const payload = (await response.json()) as { message?: string };
          if (payload?.message?.trim()) {
            message = payload.message.trim();
          }
        } catch {
          // ignore parse errors and show fallback message
        }
        setModalError(message);
        return;
      }

      setIsBookingModalOpen(false);
      await loadDirectory();
    } catch {
      setModalError("Не удалось добавить запись");
    } finally {
      setIsSubmittingBooking(false);
    }
  }

  function moveDate(step: number) {
    setSelectedDate((prev) => {
      const next = new Date(prev);
      next.setDate(prev.getDate() + step);
      return next;
    });
  }

  return (
    <section className={styles.content}>
      <div className={styles.headerRow}>
        <div>
          <h2 className={styles.pageTitle}>Расписание и записи</h2>
          <p className={styles.pageSubtitle}>Управление записями клиентов</p>
        </div>

        <div className={styles.actions}>
          <button type="button" className={styles.settingsButton}>
            <img src="/setting.svg" alt="" aria-hidden />
            <span>График работы специалиста</span>
          </button>
          <button type="button" className={styles.addButton} onClick={openBookingModal}>
            <span className={styles.plus}>+</span>
            <span>Добавить запись</span>
          </button>
        </div>
      </div>

      <section className={styles.dateCard}>
        <button type="button" className={styles.dateArrow} onClick={() => moveDate(-1)} aria-label="Предыдущий день">
          &lt;
        </button>
        <div className={styles.dateBody}>
          <p className={styles.dateTitle}>{formatDateTitle(selectedDate)}</p>
          <p className={styles.dateWeekday}>{RUS_WEEKDAY[selectedDay]}</p>
        </div>
        <button type="button" className={styles.dateArrow} onClick={() => moveDate(1)} aria-label="Следующий день">
          &gt;
        </button>
      </section>

      <section className={styles.tableWrap}>
        <div className={styles.timeRail}>
          <div className={`${styles.timeRailHeader} ${styles.sticky}`}>Время</div>
          {HOURS.map((hour) => (
            <div key={`time-${hour}`} className={styles.timeMark}>
              <span className={styles.timeMarkLabel}>{`${String(hour).padStart(2, "0")}:00`}</span>
            </div>
          ))}
        </div>

        <div className={styles.gridSurface}>
          <div
            className={styles.grid}
            style={{ gridTemplateColumns: `repeat(${Math.max(activeSpecialists.length, 1)}, minmax(180px, 1fr))` }}
          >
            {activeSpecialists.map((specialist) => (
              <div key={specialist.id} className={`${styles.headerCell} ${styles.sticky}`}>
                <strong>{specialist.full_name}</strong>
                {specialist.description?.trim() ? <span>{specialist.description}</span> : null}
              </div>
            ))}

            {HOURS.map((hour) => {
              return (
                <Fragment key={`row-${hour}`}>
                  {activeSpecialists.map((specialist) => {
                    const slotEntries = bookingsBySlot.get(`${hour}-${specialist.id}`) || [];

                    return (
                      <div
                        key={`slot-${hour}-${specialist.id}`}
                        className={`${styles.slotCell} ${slotEntries.length ? styles.slotCellWithBooking : ""}`}
                      >
                        {slotEntries.map((entry) => (
                          <article
                            key={entry.booking.id}
                            className={`${styles.bookingCard} ${styles[`bookingCard${getStatusTone(entry.booking.status).charAt(0).toUpperCase()}${getStatusTone(entry.booking.status).slice(1)}`]}`}
                            style={{
                              marginTop: `${Math.min(75, Math.max(0, Math.round((entry.minutes / 60) * 76)))}px`,
                              minHeight: `${Math.max(22, Math.round((entry.durationMinutes / 60) * 76))}px`,
                            }}
                          >
                            <button
                              type="button"
                              className={styles.bookingEditButton}
                              onClick={() => openEditBookingModal(entry.booking)}
                              aria-label="Редактировать запись"
                            >
                              <img src="/change.svg" alt="" aria-hidden />
                            </button>
                            <p className={styles.bookingStatus}>{getStatusLabel(entry.booking.status)}</p>
                            <p className={styles.bookingService}>{entry.booking.service_name}</p>
                            <p className={styles.bookingClient}>{entry.booking.client_name}</p>
                            <p className={styles.bookingTime}>
                              {formatBookingTime(entry.booking.starts_at)} - {addMinutesToTimeLabel(entry.booking.starts_at, entry.durationMinutes)}
                            </p>
                          </article>
                        ))}
                      </div>
                    );
                  })}
                </Fragment>
              );
            })}
          </div>
        </div>

        {activeSpecialists.length === 0 ? (
          <div className={styles.emptyState}>Нет активных специалистов для отображения графика.</div>
        ) : null}
      </section>

      {isBookingModalOpen ? (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Добавить запись">
          <form className={styles.bookingModal} onSubmit={submitBooking}>
            <header className={styles.bookingHeader}>
              <div className={styles.bookingTitleWrap}>
                <img src="/modal_icon.svg" alt="" aria-hidden className={styles.bookingHeaderIcon} />
                <h3>{bookingModalMode === "edit" ? "Редактировать запись" : "Добавить запись"}</h3>
              </div>
              <button type="button" className={styles.closeModalButton} onClick={closeBookingModal} aria-label="Закрыть">
                ×
              </button>
            </header>

            <div className={styles.bookingBody}>
              <label className={styles.fieldBlock}>
                <span>ФИО *</span>
                <input
                  value={bookingClientName}
                  onChange={(event) => setBookingClientName(event.target.value)}
                  required
                  maxLength={120}
                />
              </label>

              <label className={styles.fieldBlock}>
                <span>Телефон *</span>
                <input
                  value={bookingPhone}
                  onChange={(event) => setBookingPhone(event.target.value)}
                  required
                  maxLength={24}
                />
              </label>

              {bookingLines.map((line, index) => (
                <div key={line.id} className={styles.serviceRow}>
                  <label className={styles.fieldBlock}>
                    <span>Услуга{index === 0 ? "" : ` ${index + 1}`}</span>
                    <select value={line.serviceId} onChange={(event) => onServiceChange(line.id, event.target.value)}>
                      <option value="">Выберите услугу (3 уровень)</option>
                      {bookableServices.map((service) => (
                        <option key={service.id} value={String(service.id)}>
                          {service.kind_name?.trim() || service.name}
                        </option>
                      ))}
                    </select>
                    {bookableServices.length === 0 ? <span className={styles.helperError}>Нет услуг 3 уровня для записи</span> : null}
                  </label>

                  <label className={`${styles.fieldBlock} ${styles.sumField}`}>
                    <span>Сумма</span>
                    <input value={line.sum} onChange={(event) => onSumChange(line.id, event.target.value)} inputMode="numeric" />
                  </label>
                </div>
              ))}

              <label className={styles.fieldBlock}>
                <span>Специалист</span>
                <select value={bookingSpecialistId} onChange={(event) => setBookingSpecialistId(event.target.value)}>
                  <option value="">Выберите специалиста</option>
                  {availableSpecialistsForService.map((specialist) => (
                    <option key={specialist.id} value={String(specialist.id)}>
                      {specialist.full_name}
                    </option>
                  ))}
                </select>
                {primarySelectedService && availableSpecialistsForService.length === 0 ? (
                  <span className={styles.helperError}>Нет специалистов для выбранной услуги</span>
                ) : null}
              </label>

              <div className={styles.dateTimeRow}>
                <label className={styles.fieldBlock}>
                  <span>Дата</span>
                  <div className={styles.iconInputWrap}>
                    <img src="/calendar.svg" alt="" aria-hidden />
                    <input type="date" value={bookingDate} onChange={(event) => setBookingDate(event.target.value)} className={styles.dateTimeInput} />
                  </div>
                </label>

                <label className={styles.fieldBlock}>
                  <span>Время начала</span>
                  <div className={styles.iconInputWrap}>
                    <img src="/schedule.svg" alt="" aria-hidden />
                    <input type="time" value={bookingStartTime} onChange={(event) => setBookingStartTime(event.target.value)} className={styles.dateTimeInput} />
                  </div>
                </label>
              </div>

              <button type="button" className={styles.addMoreButton} onClick={addBookingLine}>
                <span>+</span>
                Добавить ещё
              </button>

              {modalError ? <p className={styles.modalError}>{modalError}</p> : null}

              <div className={styles.bookingFooter}>
                <button type="button" className={styles.cancelModalButton} onClick={closeBookingModal}>
                  Отменить
                </button>
                <button type="submit" className={styles.submitModalButton} disabled={!canSubmitBooking || isSubmittingBooking}>
                  {isSubmittingBooking ? "Сохранение..." : bookingModalMode === "edit" ? "Сохранить" : "Добавить запись"}
                </button>
              </div>
            </div>
          </form>
        </div>
      ) : null}
    </section>
  );
}
