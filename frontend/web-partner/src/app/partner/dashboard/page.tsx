"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type Booking = {
  id: number;
  service_name: string;
  manager_name: string | null;
  starts_at: string;
  client_name: string;
  client_phone: string;
  status: string;
};

type Service = {
  id: number;
  name: string;
  price: string | null;
  discount_percent: number;
  is_subscription: boolean;
};

type RowItem = Booking & {
  date: string;
  service: string;
  subscription: string;
  sum: number | null;
  statusLabel: string;
};

type DateField = "from" | "to";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

const STATUS_LABELS: Record<string, string> = {
  booked: "Запланирована",
  completed: "Завершена",
  cancelled: "Отменена",
  no_show: "Неявка",
};

const RUS_MONTHS = [
  "январь", "февраль", "март", "апрель", "май", "июнь",
  "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
];

function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function toDateKey(value: string) {
  const match = value.match(/^(\d{4}-\d{2}-\d{2})/);
  return match?.[1] ?? "";
}

function formatDateInput(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : "Выберите дату";
}

function toCalendarDate(value: string) {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  return match ? new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3])) : new Date();
}

function toDateValue(date: Date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function parseServiceNames(value: string) {
  return value.split(/\r?\n/).map((name) => name.trim()).filter(Boolean);
}

function formatTenge(value: number) {
  return `${new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(value)} ₸`;
}

function Badge({ value, type }: { value: string; type: "status" | "subscription" }) {
  const className =
    type === "status"
      ? value === "Неявка" || value === "Отменена"
        ? styles.badgeDanger
        : value === "Завершена"
          ? styles.badgeSuccess
          : styles.badgeMuted
      : value === "Доступна"
        ? styles.badgeSuccess
        : styles.badgeMuted;

  return <span className={className}>{value}</span>;
}

export default function PartnerDashboardPage() {
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [partnerEmail, setPartnerEmail] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [serviceFilter, setServiceFilter] = useState("all");
  const [specialistFilter, setSpecialistFilter] = useState("all");
  const [isFiltersOpen, setIsFiltersOpen] = useState(false);
  const [openDateField, setOpenDateField] = useState<DateField | null>(null);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date());
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { email?: string; username?: string };
      setPartnerEmail((parsed.email || parsed.username || "").trim().toLowerCase());
    } catch {
      setPartnerEmail("");
    }
  }, []);

  useEffect(() => {
    if (!partnerEmail) return;

    async function loadDashboard() {
      setIsLoading(true);
      setLoadError("");
      try {
        const [bookingsResponse, servicesResponse] = await Promise.all([
          fetch("/api/partner/bookings/", { headers: { "X-Partner-Email": partnerEmail }, cache: "no-store" }),
          fetch(`${API_BASE}/partner/services/`, {
            headers: { "X-Tenant": TENANT_DEFAULT, "X-Partner-Email": partnerEmail },
            cache: "no-store",
          }),
        ]);
        if (!bookingsResponse.ok || !servicesResponse.ok) throw new Error("load failed");
        const bookingsPayload = (await bookingsResponse.json()) as { items?: Booking[] };
        const servicesPayload = (await servicesResponse.json()) as Service[];
        setBookings(Array.isArray(bookingsPayload.items) ? bookingsPayload.items : []);
        setServices(Array.isArray(servicesPayload) ? servicesPayload : []);
      } catch {
        setBookings([]);
        setServices([]);
        setLoadError("Не удалось загрузить записи. Попробуйте обновить страницу.");
      } finally {
        setIsLoading(false);
      }
    }

    void loadDashboard();
  }, [partnerEmail]);

  const rows = useMemo<RowItem[]>(() => {
    const servicesByName = new Map(services.map((service) => [service.name.trim().toLowerCase(), service]));
    return bookings.map((booking) => {
      const bookedServices = parseServiceNames(booking.service_name);
      const relatedServices = bookedServices.map((name) => servicesByName.get(name.toLowerCase())).filter(Boolean) as Service[];
      const calculatedSum = relatedServices.reduce((total, service) => {
        const price = Number(service.price || 0);
        return total + price * (1 - Math.min(100, Math.max(0, service.discount_percent || 0)) / 100);
      }, 0);
      return {
        ...booking,
        date: formatDateTime(booking.starts_at),
        service: bookedServices.join(", ") || "Не указана",
        subscription: relatedServices.length > 0 && relatedServices.every((service) => service.is_subscription) ? "Доступна" : "Нет",
        sum: booking.status === "no_show" ? null : calculatedSum,
        statusLabel: STATUS_LABELS[booking.status] || booking.status || "Запланирована",
      };
    });
  }, [bookings, services]);

  const calendarDays = useMemo(() => {
    const monthStart = new Date(calendarMonth.getFullYear(), calendarMonth.getMonth(), 1);
    const gridStart = new Date(monthStart);
    gridStart.setDate(monthStart.getDate() - ((monthStart.getDay() + 6) % 7));
    return Array.from({ length: 42 }, (_, index) => {
      const date = new Date(gridStart);
      date.setDate(gridStart.getDate() + index);
      return date;
    });
  }, [calendarMonth]);

  const filteredRows = useMemo(() => rows.filter((row) => {
    const dateKey = toDateKey(row.starts_at);
    if (dateFrom && dateKey < dateFrom) return false;
    if (dateTo && dateKey > dateTo) return false;
    if (statusFilter !== "all" && row.status !== statusFilter) return false;
    if (serviceFilter !== "all" && !parseServiceNames(row.service_name).some((name) => name === serviceFilter)) return false;
    if (specialistFilter !== "all" && (row.manager_name || "Не назначен") !== specialistFilter) return false;
    return true;
  }), [rows, dateFrom, dateTo, statusFilter, serviceFilter, specialistFilter]);

  const stats = useMemo(() => [
    { label: "Всего записей", value: String(filteredRows.length) },
    { label: "Завершено", value: String(filteredRows.filter((row) => row.status === "completed").length) },
    { label: "Выручка", value: formatTenge(filteredRows.filter((row) => row.status === "completed").reduce((sum, row) => sum + (row.sum ?? 0), 0)) },
  ], [filteredRows]);

  const statusOptions = [...new Set(bookings.map((booking) => booking.status).filter(Boolean))];
  const serviceOptions = [...new Set(services.map((service) => service.name).filter(Boolean))].sort();
  const specialistOptions = [...new Set(bookings.map((booking) => booking.manager_name || "Не назначен"))].sort();

  function resetFilters() {
    setDateFrom("");
    setDateTo("");
    setStatusFilter("all");
    setServiceFilter("all");
    setSpecialistFilter("all");
  }

  function openCalendar(field: DateField) {
    const currentValue = field === "from" ? dateFrom : dateTo;
    const currentDate = toCalendarDate(currentValue);
    setCalendarMonth(new Date(currentDate.getFullYear(), currentDate.getMonth(), 1));
    setOpenDateField((previous) => previous === field ? null : field);
  }

  function selectCalendarDate(date: Date) {
    const value = toDateValue(date);
    if (openDateField === "from") setDateFrom(value);
    if (openDateField === "to") setDateTo(value);
    setOpenDateField(null);
  }

  return (
    <section className={styles.content}>
      <div className={styles.contentHeading}>
        <h2 className={styles.pageTitle}>Статистика</h2>
        <p className={styles.pageSubtitle}>Аналитика записей и выгрузка данных</p>
      </div>

      <section className={styles.statsRow}>
        {stats.map((item) => <article key={item.label} className={styles.statCard}><p>{item.label}</p><strong>{item.value}</strong></article>)}
      </section>

      <section className={styles.filtersBox}>
        <div className={styles.filterInputs}>
          {(["from", "to"] as DateField[]).map((field) => {
            const value = field === "from" ? dateFrom : dateTo;
            const isOpen = openDateField === field;
            return <div key={field} className={styles.inputGroup}>
              <span>{field === "from" ? "Период с" : "Период по"}</span>
              <button type="button" className={styles.datePickerButton} onClick={() => openCalendar(field)} aria-expanded={isOpen}>
                <span className={styles.calendarGlyph} aria-hidden="true" />
                {formatDateInput(value)}
              </button>
              {isOpen && <div className={styles.calendarPopover} role="dialog" aria-label={field === "from" ? "Выбор начальной даты" : "Выбор конечной даты"}>
                <header className={styles.calendarHeader}>
                  <button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Предыдущий месяц">‹</button>
                  <strong>{`${RUS_MONTHS[calendarMonth.getMonth()]} ${calendarMonth.getFullYear()}`}</strong>
                  <button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Следующий месяц">›</button>
                </header>
                <div className={styles.calendarWeekdays}>{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => <span key={day}>{day}</span>)}</div>
                <div className={styles.calendarDays}>{calendarDays.map((date) => {
                  const dateValue = toDateValue(date);
                  const isCurrentMonth = date.getMonth() === calendarMonth.getMonth();
                  return <button key={dateValue} type="button" className={`${styles.calendarDay} ${isCurrentMonth ? "" : styles.calendarDayMuted} ${dateValue === value ? styles.calendarDaySelected : ""}`} onClick={() => selectCalendarDate(date)}>{date.getDate()}</button>;
                })}</div>
              </div>}
            </div>;
          })}
        </div>
        <div className={styles.filterActions}>
          <button type="button" className={styles.filterButton} onClick={() => setIsFiltersOpen((value) => !value)} aria-expanded={isFiltersOpen}>
            <span className={styles.filterIcon} aria-hidden="true" />
            Фильтры
          </button>
          <button type="button" className={styles.resetButton} onClick={resetFilters}>Сбросить</button>
        </div>
      </section>

      {isFiltersOpen && <section className={styles.advancedFilters} aria-label="Дополнительные фильтры">
        <label className={styles.selectGroup}>Статус<select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">Все статусы</option>{statusOptions.map((status) => <option key={status} value={status}>{STATUS_LABELS[status] || status}</option>)}</select></label>
        <label className={styles.selectGroup}>Услуга<select value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)}><option value="all">Все услуги</option>{serviceOptions.map((service) => <option key={service} value={service}>{service}</option>)}</select></label>
        <label className={styles.selectGroup}>Специалист<select value={specialistFilter} onChange={(event) => setSpecialistFilter(event.target.value)}><option value="all">Все специалисты</option>{specialistOptions.map((specialist) => <option key={specialist} value={specialist}>{specialist}</option>)}</select></label>
      </section>}

      <div className={styles.tableBox}>
        <table className={styles.table}>
          <thead><tr><th className={styles.wDate}>Дата и время</th><th>ФИО клиента</th><th>Телефон</th><th>Услуги</th><th>Специалист</th><th className={styles.wStatus}>Статус</th><th className={styles.wStatus}>Подписка</th><th className={styles.wSum}>Сумма</th></tr></thead>
          <tbody>
            {isLoading && <tr><td colSpan={8} className={styles.emptyState}>Загрузка записей...</td></tr>}
            {!isLoading && loadError && <tr><td colSpan={8} className={styles.emptyState}>{loadError}</td></tr>}
            {!isLoading && !loadError && filteredRows.length === 0 && <tr><td colSpan={8} className={styles.emptyState}>Записей по выбранным фильтрам нет.</td></tr>}
            {!isLoading && !loadError && filteredRows.map((row) => <tr key={row.id}><td>{row.date}</td><td>{row.client_name}</td><td>{row.client_phone}</td><td>{row.service}</td><td>{row.manager_name || "Не назначен"}</td><td className={styles.center}><Badge value={row.statusLabel} type="status" /></td><td className={styles.center}><Badge value={row.subscription} type="subscription" /></td><td>{row.sum === null ? "-" : formatTenge(row.sum)}</td></tr>)}
          </tbody>
        </table>
      </div>
    </section>
  );
}
