"use client";

import { FormEvent, Fragment, useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";
import { formatRuPhone } from "../../../../lib/phone";

type WorkingDayKey = "mon" | "tue" | "wed" | "thu" | "fri" | "sat" | "sun";

type ScheduleBreak = {
  name: string;
  start_time: string;
  end_time: string;
};

type WorkingDaySchedule = {
  day: WorkingDayKey;
  date?: string;
  is_day_off: boolean;
  start_time: string;
  end_time: string;
  break_start: string;
  break_end: string;
  discount_start: string;
  discount_end: string;
  breaks: ScheduleBreak[];
};

type Specialist = {
  id: number;
  full_name: string;
  description?: string;
  photo_url?: string;
  working_schedule: WorkingDaySchedule[];
  service_ids?: number[];
  is_active: boolean;
};

type Service = {
  id: number;
  name: string;
  kind: number | null;
  kind_name?: string | null;
  duration_minutes?: number;
  price: string | null;
  discount_percent?: number;
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
type SpecialistDayStateTone = "working" | "dayoff" | "break" | "discount";
type SpecialistDayState = {
  tone: SpecialistDayStateTone;
  label: string;
  hoursLabel: string;
};

type SpecialistSlotState = {
  tone: SpecialistDayStateTone;
  label: string;
};

type CalendarBooking = {
  booking: Booking;
  minutes: number;
  durationMinutes: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
const WEEK_DAYS: WorkingDayKey[] = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

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
const SLOT_HEIGHT = 56;
const CLOSED_BOOKING_STATUSES = ["cancelled", "canceled", "отменен", "отменена", "completed", "done", "завершен", "завершена", "no_show", "no-show", "missed", "неявка"];
const WORKING_DAYS: { key: WorkingDayKey; label: string }[] = [
  { key: "mon", label: "Понедельник" },
  { key: "tue", label: "Вторник" },
  { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" },
  { key: "fri", label: "Пятница" },
  { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" },
];

function defaultWorkingSchedule(): WorkingDaySchedule[] {
  return WORKING_DAYS.map(({ key }) => ({
    day: key,
    is_day_off: true,
    start_time: "",
    end_time: "",
    break_start: "",
    break_end: "",
    discount_start: "",
    discount_end: "",
    breaks: [],
  }));
}

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

function normalizeWorkingSchedule(raw: unknown): WorkingDaySchedule[] {
  const fallback = WEEK_DAYS.map((day) => ({
    day,
    is_day_off: true,
    start_time: "",
    end_time: "",
    break_start: "",
    break_end: "",
    discount_start: "",
    discount_end: "",
    breaks: [],
  }));

  if (!Array.isArray(raw)) {
    return fallback;
  }

  const byDay = new Map<WorkingDayKey, WorkingDaySchedule>();
  const overrides: WorkingDaySchedule[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") {
      continue;
    }

    const item = entry as Partial<WorkingDaySchedule> & { day?: string };
    const day = item.day;
    if (!day || !WEEK_DAYS.includes(day as WorkingDayKey)) {
      continue;
    }

    const legacyBreakStart = typeof item.break_start === "string" ? item.break_start : "";
    const legacyBreakEnd = typeof item.break_end === "string" ? item.break_end : "";
    const breaks = Array.isArray(item.breaks)
      ? item.breaks
          .filter((scheduleBreak): scheduleBreak is ScheduleBreak => Boolean(scheduleBreak && typeof scheduleBreak === "object"))
          .map((scheduleBreak) => ({
            name: typeof scheduleBreak.name === "string" ? scheduleBreak.name : "Перерыв",
            start_time: typeof scheduleBreak.start_time === "string" ? scheduleBreak.start_time : "",
            end_time: typeof scheduleBreak.end_time === "string" ? scheduleBreak.end_time : "",
          }))
      : legacyBreakStart && legacyBreakEnd
        ? [{ name: "Обед", start_time: legacyBreakStart, end_time: legacyBreakEnd }]
        : [];
    const normalizedItem: WorkingDaySchedule = {
      day: day as WorkingDayKey,
      ...(typeof item.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(item.date) ? { date: item.date } : {}),
      is_day_off: Boolean(item.is_day_off),
      start_time: typeof item.start_time === "string" ? item.start_time : "",
      end_time: typeof item.end_time === "string" ? item.end_time : "",
      break_start: breaks[0]?.start_time ?? "",
      break_end: breaks[0]?.end_time ?? "",
      discount_start: typeof item.discount_start === "string" ? item.discount_start : "10:00",
      discount_end: typeof item.discount_end === "string" ? item.discount_end : "16:00",
      breaks,
    };
    if (normalizedItem.date) {
      overrides.push(normalizedItem);
    } else {
      byDay.set(day as WorkingDayKey, normalizedItem);
    }
  }

  return [...WEEK_DAYS.map((day) => byDay.get(day) ?? fallback.find((item) => item.day === day)!).filter(Boolean), ...overrides];
}

function getScheduleForDate(schedule: WorkingDaySchedule[], date: Date): WorkingDaySchedule | undefined {
  const dateKey = formatDateInputValue(date);
    return schedule.find((item) => item.date === dateKey) ?? schedule.find((item) => item.day === toWorkingDayKey(date) && !item.date) ?? undefined;
}

function getSpecialistDayState(specialist: Specialist, selectedDay: WorkingDayKey): SpecialistDayState {
  const schedule = normalizeWorkingSchedule(specialist.working_schedule);
    const day = schedule.find((item) => item.day === selectedDay) ?? { is_day_off: true, start_time: "", end_time: "" };

  if (!day || day.is_day_off) {
    return {
      tone: "dayoff",
      label: "Выходной",
      hoursLabel: "Нет приема",
    };
  }

  const workLabel = day.start_time && day.end_time ? `${day.start_time}-${day.end_time}` : "Время не задано";
  if (day.break_start && day.break_end) {
    return {
      tone: "break",
      label: `Перерыв ${day.break_start}-${day.break_end}`,
      hoursLabel: `Рабочее время ${workLabel}`,
    };
  }

  return {
    tone: "working",
    label: "Рабочий",
    hoursLabel: workLabel,
  };
}

function toMinutes(value: string): number | null {
  const match = value.match(/^(\d{2}):(\d{2})$/);
  if (!match) {
    return null;
  }
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  return hours * 60 + minutes;
}

function getSpecialistSlotState(day: WorkingDaySchedule | undefined, hour: number): SpecialistSlotState {
  if (!day || day.is_day_off) {
    return { tone: "dayoff", label: "Выходной" };
  }

  const slotStart = hour * 60;
  const slotEnd = (hour + 1) * 60;
  const intersectsBreak = day.breaks.some((scheduleBreak) => {
    const breakStart = toMinutes(scheduleBreak.start_time);
    const breakEnd = toMinutes(scheduleBreak.end_time);
    return breakStart != null && breakEnd != null && breakStart < slotEnd && breakEnd > slotStart;
  });
  if (intersectsBreak) {
    return { tone: "break", label: "Перерыв" };
  }

  const discountStart = toMinutes(day.discount_start);
  const discountEnd = toMinutes(day.discount_end);
  if (discountStart != null && discountEnd != null && discountStart < slotEnd && discountEnd > slotStart) {
    return { tone: "discount", label: "Время скидки" };
  }

  return { tone: "working", label: "Рабочий" };
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
  const [detailsBooking, setDetailsBooking] = useState<Booking | null>(null);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [isDetailsMenuOpen, setIsDetailsMenuOpen] = useState(false);
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [isDeletingBooking, setIsDeletingBooking] = useState(false);
  const [draggedLineId, setDraggedLineId] = useState<number | null>(null);
  const [dragEnabledLineId, setDragEnabledLineId] = useState<number | null>(null);
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
  const [isBulkScheduleOpen, setIsBulkScheduleOpen] = useState(false);
  const [bulkScheduleDraft, setBulkScheduleDraft] = useState<WorkingDaySchedule[]>(defaultWorkingSchedule());
  const [scheduleSpecialistId, setScheduleSpecialistId] = useState("");
  const [selectedScheduleDateKeys, setSelectedScheduleDateKeys] = useState<string[]>([]);
  const [bulkScheduleError, setBulkScheduleError] = useState("");
  const [isSavingBulkSchedule, setIsSavingBulkSchedule] = useState(false);
  const [isDatePickerOpen, setIsDatePickerOpen] = useState(false);
  const [calendarMonth, setCalendarMonth] = useState(() => new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));

  const activeSpecialists = useMemo(
    () => specialists.filter((specialist) => specialist.is_active).sort((a, b) => a.full_name.localeCompare(b.full_name)),
    [specialists],
  );

  const selectedDay = toWorkingDayKey(selectedDate);

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

  const activeServices = useMemo(() => {
    return services.filter((service) => service.is_active).sort((a, b) => a.name.localeCompare(b.name));
  }, [services]);

  const bookableServices = useMemo(() => {
    return activeServices;
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
    const selectedServiceIds = selectedServicesInModal.map((service) => service.id);
    if (!selectedServiceIds.length) {
      return activeSpecialists;
    }
    return activeSpecialists.filter((specialist) => {
      const assignedServiceIds = specialist.service_ids ?? [];
      return selectedServiceIds.every((serviceId) => assignedServiceIds.includes(serviceId));
    });
  }, [activeSpecialists, selectedServicesInModal]);

  const availableServicesForSpecialist = useMemo(() => {
    if (!bookingSpecialistId) {
      return bookableServices;
    }
    const specialist = activeSpecialists.find((item) => String(item.id) === bookingSpecialistId);
    if (!specialist) {
      return bookableServices;
    }
    const assignedServiceIds = specialist.service_ids ?? [];
    return bookableServices.filter((service) => assignedServiceIds.includes(service.id));
  }, [activeSpecialists, bookableServices, bookingSpecialistId]);

  const canSubmitBooking = useMemo(() => {
    if (!bookingClientName.trim() || !bookingPhone.trim() || !bookingDate || !bookingStartTime || !bookingSpecialistId) {
      return false;
    }
    return bookingLines.some((line) => line.serviceId);
  }, [bookingClientName, bookingPhone, bookingDate, bookingStartTime, bookingSpecialistId, bookingLines]);

  const detailsServices = useMemo(() => {
    if (!detailsBooking) {
      return [];
    }
    const startsAt = parseBookingDateTime(detailsBooking.starts_at);
    const specialist = activeSpecialists.find(
      (item) => item.full_name.trim().toLowerCase() === (detailsBooking.manager_name || "").trim().toLowerCase(),
    );
    const daySchedule =
      startsAt && specialist
        ? getScheduleForDate(normalizeWorkingSchedule(specialist.working_schedule), new Date(`${startsAt.dateKey}T12:00:00`))
        : undefined;
    const discountStart = daySchedule && !daySchedule.is_day_off ? toMinutes(daySchedule.discount_start) : null;
    const discountEnd = daySchedule && !daySchedule.is_day_off ? toMinutes(daySchedule.discount_end) : null;
    let minutesBefore = 0;

    return parseServiceNames(detailsBooking.service_name).map((serviceName) => {
      const service = services.find(
        (item) =>
          item.name.trim().toLowerCase() === serviceName.toLowerCase() ||
          (item.kind_name || "").trim().toLowerCase() === serviceName.toLowerCase(),
      );
      const price = Number(String(service?.price || "").replace(/[^0-9.,]/g, "").replace(",", "."));
      const durationMinutes = service?.duration_minutes && service.duration_minutes > 0 ? service.duration_minutes : 60;
      const serviceStart = startsAt ? startsAt.hour * 60 + startsAt.minutes + minutesBefore : null;
      const serviceEnd = serviceStart == null ? null : serviceStart + durationMinutes;
      minutesBefore += durationMinutes;
      // Скидка действует, только если услуга целиком попадает в скидочное окно специалиста.
      const isDiscountTime =
        discountStart != null &&
        discountEnd != null &&
        serviceStart != null &&
        serviceEnd != null &&
        serviceStart >= discountStart &&
        serviceEnd <= discountEnd;

      return {
        name: serviceName,
        price: Number.isFinite(price) ? price : null,
        discountPercent: isDiscountTime ? Math.max(0, Math.min(100, Number(service?.discount_percent || 0))) : 0,
        durationMinutes,
      };
    });
  }, [detailsBooking, services, activeSpecialists]);

  // Порядок услуг задаёт их время, поэтому скидка считается по накопленной длительности.
  const bookingDiscountByLineId = useMemo(() => {
    const result = new Map<number, { price: number; discountPercent: number }>();
    const specialist = activeSpecialists.find((item) => String(item.id) === bookingSpecialistId);
    const daySchedule =
      specialist && bookingDate
        ? getScheduleForDate(normalizeWorkingSchedule(specialist.working_schedule), new Date(`${bookingDate}T12:00:00`))
        : undefined;
    const discountStart = daySchedule && !daySchedule.is_day_off ? toMinutes(daySchedule.discount_start) : null;
    const discountEnd = daySchedule && !daySchedule.is_day_off ? toMinutes(daySchedule.discount_end) : null;
    const startMinutes = toMinutes(bookingStartTime);
    let minutesBefore = 0;

    for (const line of bookingLines) {
      const service = bookableServices.find((item) => String(item.id) === line.serviceId);
      if (!service) {
        continue;
      }
      const durationMinutes = service.duration_minutes && service.duration_minutes > 0 ? service.duration_minutes : 60;
      const rawPrice = String(line.sum || service.price || "").replace(/[^0-9.,]/g, "").replace(",", ".");
      const price = Number(rawPrice);
      const serviceStart = startMinutes == null ? null : startMinutes + minutesBefore;
      const serviceEnd = serviceStart == null ? null : serviceStart + durationMinutes;
      minutesBefore += durationMinutes;
      const isDiscountTime =
        discountStart != null &&
        discountEnd != null &&
        serviceStart != null &&
        serviceEnd != null &&
        serviceStart >= discountStart &&
        serviceEnd <= discountEnd;

      result.set(line.id, {
        price: Number.isFinite(price) ? price : 0,
        discountPercent: isDiscountTime ? Math.max(0, Math.min(100, Number(service.discount_percent || 0))) : 0,
      });
    }

    return result;
  }, [bookingLines, bookableServices, bookingSpecialistId, bookingDate, bookingStartTime, activeSpecialists]);

  const detailsSpecialist = useMemo(    () => activeSpecialists.find((item) => item.full_name.trim().toLowerCase() === (detailsBooking?.manager_name || "").trim().toLowerCase()),
    [activeSpecialists, detailsBooking],
  );

  const selectedDayScheduleBySpecialist = useMemo(() => {
    const map = new Map<number, WorkingDaySchedule | undefined>();
    for (const specialist of activeSpecialists) {
      const daySchedule = getScheduleForDate(normalizeWorkingSchedule(specialist.working_schedule), selectedDate);
      map.set(specialist.id, daySchedule);
    }
    return map;
  }, [activeSpecialists, selectedDay]);

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
    const specialistByName = new Map<string, Specialist>();
    for (const specialist of activeSpecialists) {
      specialistByName.set(specialist.full_name.trim().toLowerCase(), specialist);
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
      const specialist = specialistByName.get(bookingManagerName);
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
        setSpecialists(
          Array.isArray(specialistsPayload)
            ? specialistsPayload.map((item) => ({ ...item, working_schedule: normalizeWorkingSchedule(item.working_schedule) }))
            : [],
        );
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
    setBookingClientName("");
    setBookingPhone("");
    setBookingSpecialistId("");
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

  function openDetailsModal(target: Booking) {
    setIsDetailsMenuOpen(false);
    setIsDeleteConfirmOpen(false);
    setDetailsBooking(target);
  }

  async function deleteBooking() {
    if (!detailsBooking || !partnerEmail || isDeletingBooking) {
      return;
    }

    setIsDeletingBooking(true);
    try {
      const response = await fetch(`/api/partner/bookings/${detailsBooking.id}/`, {
        method: "DELETE",
        headers: { "X-Partner-Email": partnerEmail },
      });
      if (!response.ok) {
        return;
      }
      setIsDeleteConfirmOpen(false);
      setDetailsBooking(null);
      await loadDirectory();
    } finally {
      setIsDeletingBooking(false);
    }
  }

  async function updateBookingStatus(status: "completed" | "no_show") {
    if (!detailsBooking || !partnerEmail || isUpdatingStatus) {
      return;
    }

    setIsUpdatingStatus(true);
    try {
      const response = await fetch(`/api/partner/bookings/${detailsBooking.id}/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Partner-Email": partnerEmail,
        },
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        return;
      }
      setDetailsBooking(null);
      await loadDirectory();
    } finally {
      setIsUpdatingStatus(false);
    }
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

    if (!selectedService) {
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
      const canProvideService = (currentSpecialist.service_ids ?? []).includes(selectedService.id);
      return canProvideService ? prev : "";
    });
  }

  function onSpecialistChange(specialistId: string) {
    setBookingSpecialistId(specialistId);
    const specialist = activeSpecialists.find((item) => String(item.id) === specialistId);
    if (!specialist) {
      return;
    }
    const assignedServiceIds = specialist.service_ids ?? [];
    setBookingLines((prev) =>
      prev.map((line) =>
        line.serviceId && !assignedServiceIds.includes(Number(line.serviceId))
          ? { ...line, serviceId: "", sum: "" }
          : line,
      ),
    );
  }

  function getBookingScheduleError(specialist: Specialist, dateValue: string, startTime: string, durationMinutes: number) {
    const date = new Date(`${dateValue}T12:00:00`);
    if (Number.isNaN(date.getTime())) return "Выберите корректную дату записи";
    const day = getScheduleForDate(normalizeWorkingSchedule(specialist.working_schedule), date);
    const startMinutes = toMinutes(startTime);
    if (!day || day.is_day_off) return "У специалиста выходной в выбранный день";
    if (startMinutes == null) return "Выберите время начала записи";
    const endMinutes = startMinutes + durationMinutes;
    const workStart = toMinutes(day.start_time);
    const workEnd = toMinutes(day.end_time);
    if (workStart == null || workEnd == null || startMinutes < workStart || endMinutes > workEnd) {
      return "Время записи выходит за рабочий график специалиста";
    }
    if (day.breaks.some((scheduleBreak) => {
      const breakStart = toMinutes(scheduleBreak.start_time);
      const breakEnd = toMinutes(scheduleBreak.end_time);
      return breakStart != null && breakEnd != null && startMinutes < breakEnd && breakStart < endMinutes;
    })) {
      return "Запись пересекается с перерывом специалиста";
    }
    return "";
  }

  function onSumChange(lineId: number, value: string) {
    setBookingLines((prev) => prev.map((line) => (line.id === lineId ? { ...line, sum: value } : line)));
  }

  function addBookingLine() {
    setBookingLines((prev) => [...prev, { id: Date.now() + prev.length, serviceId: "", sum: "" }]);
  }

  function removeBookingLine(lineId: number) {
    setModalError("");
    setBookingLines((prev) => (prev.length === 1 ? prev : prev.filter((line) => line.id !== lineId)));
  }

  function moveBookingLine(sourceId: number, targetId: number) {
    if (sourceId === targetId) {
      return;
    }
    setBookingLines((prev) => {
      const sourceIndex = prev.findIndex((line) => line.id === sourceId);
      const targetIndex = prev.findIndex((line) => line.id === targetId);
      if (sourceIndex < 0 || targetIndex < 0) {
        return prev;
      }
      const next = [...prev];
      const [moved] = next.splice(sourceIndex, 1);
      next.splice(targetIndex, 0, moved);
      return next;
    });
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

    if (selectedServices.some((service) => !(specialist.service_ids ?? []).includes(service.id))) {
      setModalError("Выбранный специалист не оказывает эту услугу");
      return;
    }

    const scheduleError = getBookingScheduleError(
      specialist,
      bookingDate,
      bookingStartTime,
      selectedServices.reduce((total, service) => total + (service.duration_minutes && service.duration_minutes > 0 ? service.duration_minutes : 60), 0),
    );
    if (scheduleError) {
      setModalError(scheduleError);
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
        .map((service) => service.name.trim())
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
          serviceIds: selectedServices.map((service) => service.id),
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
      setCalendarMonth(new Date(next.getFullYear(), next.getMonth(), 1));
      return next;
    });
  }

  function openDatePicker() {
    setCalendarMonth(new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));
    setIsDatePickerOpen((previous) => !previous);
  }

  function openBulkScheduleModal() {
    const specialist = activeSpecialists[0];
    setScheduleSpecialistId(specialist ? String(specialist.id) : "");
    setBulkScheduleDraft(specialist ? normalizeWorkingSchedule(specialist.working_schedule) : defaultWorkingSchedule());
    setBulkScheduleError("");
    setCalendarMonth(new Date(selectedDate.getFullYear(), selectedDate.getMonth(), 1));
    setSelectedScheduleDateKeys([formatDateInputValue(selectedDate)]);
    setIsBulkScheduleOpen(true);
  }

  function changeScheduleSpecialist(specialistId: string) {
    const specialist = activeSpecialists.find((item) => String(item.id) === specialistId);
    setScheduleSpecialistId(specialistId);
    setBulkScheduleDraft(specialist ? normalizeWorkingSchedule(specialist.working_schedule) : defaultWorkingSchedule());
    setBulkScheduleError("");
  }

  function hasActiveBookingsOnSelectedDates() {
    const specialist = activeSpecialists.find((item) => String(item.id) === scheduleSpecialistId);
    if (!specialist) {
      return false;
    }
    const specialistName = specialist.full_name.trim().toLowerCase();
    return bookings.some((booking) => {
      if ((booking.manager_name || "").trim().toLowerCase() !== specialistName) {
        return false;
      }
      const parsed = parseBookingDateTime(booking.starts_at);
      if (!parsed || !selectedScheduleDateKeys.includes(parsed.dateKey)) {
        return false;
      }
      return !CLOSED_BOOKING_STATUSES.includes(booking.status.trim().toLowerCase());
    });
  }

  function toggleSelectedDayOff(day: WorkingDaySchedule) {
    if (!day.is_day_off && hasActiveBookingsOnSelectedDates()) {
      setBulkScheduleError("В расписании на этот день присутствуют активные записи. День нельзя сделать нерабочим с активными записями");
      return;
    }
    updateSelectedScheduleDays({
      is_day_off: !day.is_day_off,
      start_time: day.is_day_off ? "09:00" : "",
      end_time: day.is_day_off ? "18:00" : "",
      discount_start: day.is_day_off ? "10:00" : "",
      discount_end: day.is_day_off ? "16:00" : "",
      breaks: day.is_day_off ? [{ name: "Обед", start_time: "13:00", end_time: "14:00" }] : [],
    });
  }

  function updateSelectedScheduleDays(patch: Partial<WorkingDaySchedule>) {
    setBulkScheduleError("");
    setBulkScheduleDraft((previous) => {
      const remaining = previous.filter((item) => !item.date || !selectedScheduleDateKeys.includes(item.date));
      const overrides = selectedScheduleDateKeys.map((dateKey) => {
        const date = new Date(`${dateKey}T12:00:00`);
        const current = getScheduleForDate(previous, date) ?? defaultWorkingSchedule()[0];
        return { ...current, ...patch, date: dateKey, day: toWorkingDayKey(date) };
      });
      return [...remaining, ...overrides];
    });
  }

  function toggleScheduleDate(date: Date) {    const dateKey = formatDateInputValue(date);
    setSelectedDate(date);
    setSelectedScheduleDateKeys((previous) => {
      if (previous.includes(dateKey)) {
        return previous.length === 1 ? previous : previous.filter((item) => item !== dateKey);
      }
      return [...previous, dateKey];
    });
  }

  function validateBulkSchedule() {
    for (const day of bulkScheduleDraft) {
      if (day.is_day_off) continue;
      if (!day.start_time || !day.end_time || day.start_time >= day.end_time) {
        return "Проверьте рабочее время в каждом рабочем дне";
      }
      if (!day.discount_start || !day.discount_end || !(day.start_time <= day.discount_start && day.discount_start < day.discount_end && day.discount_end <= day.end_time)) {
        return "Время скидок должно быть внутри рабочего времени";
      }
      if (day.breaks.some((scheduleBreak) => !scheduleBreak.start_time || !scheduleBreak.end_time || !(day.start_time <= scheduleBreak.start_time && scheduleBreak.start_time < scheduleBreak.end_time && scheduleBreak.end_time <= day.end_time))) {
        return "Каждый перерыв должен быть внутри рабочего времени";
      }
      const sortedBreaks = [...day.breaks].sort((left, right) => left.start_time.localeCompare(right.start_time));
      if (sortedBreaks.some((scheduleBreak, index) => index > 0 && scheduleBreak.start_time < sortedBreaks[index - 1].end_time)) {
        return "Перерывы не должны пересекаться";
      }
    }
    return "";
  }

  async function submitBulkSchedule() {
    if (!scheduleSpecialistId || !partnerEmail || isSavingBulkSchedule) {
      setBulkScheduleError("Выберите специалиста");
      return;
    }
    const validationError = validateBulkSchedule();
    if (validationError) {
      setBulkScheduleError(validationError);
      return;
    }

    setIsSavingBulkSchedule(true);
    try {
      const response = await fetch(`${API_BASE}/partner/specialists/${scheduleSpecialistId}/`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", "X-Tenant": tenant, "X-Partner-Email": partnerEmail },
        body: JSON.stringify({ working_schedule: bulkScheduleDraft }),
      });
      if (!response.ok) {
        setBulkScheduleError("Не удалось сохранить график");
        return;
      }
      setIsBulkScheduleOpen(false);
      await loadDirectory();
    } finally {
      setIsSavingBulkSchedule(false);
    }
  }

  return (
    <section className={styles.content}>
      <div className={styles.headerRow}>
        <div>
          <h2 className={styles.pageTitle}>Расписание и записи</h2>
          <p className={styles.pageSubtitle}>Управление записями клиентов</p>
        </div>

        <div className={styles.actions}>
          <button type="button" className={styles.settingsButton} onClick={openBulkScheduleModal} disabled={!partnerEmail || !activeSpecialists.length}>
            <img src="/setting.svg" alt="" aria-hidden />
            <span>Составить график работы</span>
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
        <button type="button" className={styles.dateBody} onClick={openDatePicker} aria-label="Выбрать дату">
          <p className={styles.dateTitle}>{formatDateTitle(selectedDate)}</p>
          <p className={styles.dateWeekday}>{RUS_WEEKDAY[selectedDay]}</p>
        </button>
        <button type="button" className={styles.dateArrow} onClick={() => moveDate(1)} aria-label="Следующий день">
          &gt;
        </button>
        {isDatePickerOpen ? (
          <div className={styles.calendarPopover} role="dialog" aria-label="Выбор даты">
            <header className={styles.calendarHeader}>
              <button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Предыдущий месяц">‹</button>
              <strong>{`${RUS_MONTH[calendarMonth.getMonth()]} ${calendarMonth.getFullYear()}`}</strong>
              <button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Следующий месяц">›</button>
            </header>
            <div className={styles.calendarWeekdays}>{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => <span key={day}>{day}</span>)}</div>
            <div className={styles.calendarDays}>
              {calendarDays.map((date) => {
                const isCurrentMonth = date.getMonth() === calendarMonth.getMonth();
                const isSelected = formatDateInputValue(date) === formatDateInputValue(selectedDate);
                return (
                  <button
                    key={formatDateInputValue(date)}
                    type="button"
                    className={`${styles.calendarDay} ${isCurrentMonth ? "" : styles.calendarDayMuted} ${isSelected ? styles.calendarDaySelected : ""}`}
                    onClick={() => {
                      setSelectedDate(date);
                      setCalendarMonth(new Date(date.getFullYear(), date.getMonth(), 1));
                      setIsDatePickerOpen(false);
                    }}
                  >
                    {date.getDate()}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
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
              </div>
            ))}

            {HOURS.map((hour) => {
              return (
                <Fragment key={`row-${hour}`}>
                  {activeSpecialists.map((specialist) => {
                    const slotEntries = bookingsBySlot.get(`${hour}-${specialist.id}`) || [];
                    const daySchedule = selectedDayScheduleBySpecialist.get(specialist.id);
                    const slotState = getSpecialistSlotState(daySchedule, hour);
                    const slotStateClass = styles[`slotCell${slotState.tone.charAt(0).toUpperCase()}${slotState.tone.slice(1)}`];
                    const slotStateTextClass = styles[`slotStateText${slotState.tone.charAt(0).toUpperCase()}${slotState.tone.slice(1)}`];

                    return (
                      <div
                        key={`slot-${hour}-${specialist.id}`}
                        className={`${styles.slotCell} ${slotStateClass} ${slotEntries.length ? styles.slotCellWithBooking : ""}`}
                      >
                        {!slotEntries.length && slotState.tone === "break" ? (
                          <p className={`${styles.slotStateText} ${slotStateTextClass}`}>Тех. перерыв</p>
                        ) : null}
                        {slotEntries.map((entry) => (
                          <article
                            key={entry.booking.id}
                            className={`${styles.bookingCard} ${styles[`bookingCard${getStatusTone(entry.booking.status).charAt(0).toUpperCase()}${getStatusTone(entry.booking.status).slice(1)}`]}`}
                            onClick={() => openDetailsModal(entry.booking)}
                            style={{
                              marginTop: `${Math.min(SLOT_HEIGHT - 1, Math.max(0, Math.round((entry.minutes / 60) * SLOT_HEIGHT)))}px`,
                              minHeight: `${Math.max(28, Math.round((entry.durationMinutes / 60) * SLOT_HEIGHT))}px`,
                            }}
                          >
                            <button
                              type="button"
                              className={styles.bookingEditButton}
                              onClick={(event) => {
                                event.stopPropagation();
                                openDetailsModal(entry.booking);
                              }}
                              aria-label="Посмотреть запись"
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
                  onChange={(event) => setBookingPhone(formatRuPhone(event.target.value))}
                  required
                  maxLength={24}
                  inputMode="tel"
                />
              </label>

              {bookingLines.map((line, index) => {
                const lineDiscount = bookingDiscountByLineId.get(line.id);

                return (
                  <div
                    key={line.id}
                    className={`${styles.serviceLine} ${draggedLineId === line.id ? styles.serviceLineDragging : ""}`}
                    draggable={dragEnabledLineId === line.id}
                    onDragStart={() => setDraggedLineId(line.id)}
                    onDragEnd={() => {
                      setDraggedLineId(null);
                      setDragEnabledLineId(null);
                    }}
                    onDragOver={(event) => event.preventDefault()}
                    onDrop={(event) => {
                      event.preventDefault();
                      if (draggedLineId != null) {
                        moveBookingLine(draggedLineId, line.id);
                      }
                      setDraggedLineId(null);
                      setDragEnabledLineId(null);
                    }}
                  >
                    <div className={styles.serviceRow}>
                      {bookingLines.length > 1 ? (
                        <button
                          type="button"
                          className={styles.dragHandle}
                          onMouseDown={() => setDragEnabledLineId(line.id)}
                          onMouseUp={() => setDragEnabledLineId(null)}
                          aria-label={`Переместить услугу ${index + 1}`}
                          title="Перетащите, чтобы изменить порядок"
                        >
                          ⠿
                        </button>
                      ) : null}

                      <label className={styles.fieldBlock}>
                        <span>Услуга{index === 0 ? "" : ` ${index + 1}`}</span>
                        <select value={line.serviceId} onChange={(event) => onServiceChange(line.id, event.target.value)}>
                          <option value="">Выберите созданную услугу</option>
                          {availableServicesForSpecialist.map((service) => (
                            <option key={service.id} value={String(service.id)}>
                              {service.name}
                            </option>
                          ))}
                        </select>
                        {availableServicesForSpecialist.length === 0 ? <span className={styles.helperError}>Нет доступных услуг для записи</span> : null}
                      </label>

                      <label className={`${styles.fieldBlock} ${styles.sumField}`}>
                        <span>Сумма</span>
                        <input value={line.sum} onChange={(event) => onSumChange(line.id, event.target.value)} inputMode="numeric" />
                      </label>

                      {bookingLines.length > 1 ? (
                        <button
                          type="button"
                          className={styles.removeLineButton}
                          onClick={() => removeBookingLine(line.id)}
                          aria-label={`Удалить услугу ${index + 1}`}
                        >
                          ×
                        </button>
                      ) : null}
                    </div>

                    {lineDiscount && lineDiscount.discountPercent > 0 ? (
                      <p className={styles.discountHint}>
                        <strong>{`${Math.round(lineDiscount.price * (1 - lineDiscount.discountPercent / 100)).toLocaleString("ru-RU")} т`}</strong>
                        <s>{`${lineDiscount.price.toLocaleString("ru-RU")} т`}</s>
                        <span>{`скидка ${lineDiscount.discountPercent}%`}</span>
                      </p>
                    ) : null}
                  </div>
                );
              })}

              <label className={styles.fieldBlock}>
                <span>Специалист</span>
                <select value={bookingSpecialistId} onChange={(event) => onSpecialistChange(event.target.value)}>
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

      {detailsBooking ? (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Детали записи">
          <section className={styles.detailsModal}>
            <header className={styles.detailsHeader}>
              <div className={styles.detailsTitle}>
                <img src="/modal_icon.svg" alt="" aria-hidden />
                <h3>Детали записи</h3>
              </div>
              <div className={styles.detailsHeaderActions}>
                <button
                  type="button"
                  className={styles.detailsMenuButton}
                  onClick={() => setIsDetailsMenuOpen((previous) => !previous)}
                  aria-label="Действия с записью"
                  aria-expanded={isDetailsMenuOpen}
                >
                  ⋯
                </button>
                {isDetailsMenuOpen ? (
                  <div className={styles.detailsMenu} role="menu">
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        setIsDetailsMenuOpen(false);
                        setDetailsBooking(null);
                        openEditBookingModal(detailsBooking);
                      }}
                    >
                      Редактировать
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      className={styles.detailsMenuDanger}
                      onClick={() => {
                        setIsDetailsMenuOpen(false);
                        setIsDeleteConfirmOpen(true);
                      }}
                    >
                      Удалить
                    </button>
                  </div>
                ) : null}
                <button
                  type="button"
                  className={styles.closeModalButton}
                  onClick={() => {
                    setIsDetailsMenuOpen(false);
                    setDetailsBooking(null);
                  }}
                  aria-label="Закрыть"
                >
                  ×
                </button>
              </div>
            </header>

            <div className={styles.detailsBody}>
              <div className={styles.clientSummary}>
                <div className={styles.clientAvatar}>{detailsBooking.client_name.trim().slice(0, 1).toUpperCase() || "К"}</div>
                <div>
                  <strong>{detailsBooking.client_name}</strong>
                  <span>{formatRuPhone(detailsBooking.client_phone)}</span>
                </div>
                <div className={styles.subscriptionStatus}>
                  <span>Подписка</span>
                  <strong>Активна</strong>
                </div>
              </div>

              <div className={styles.detailServices}>
                {detailsServices.map((service, index) => {
                  const minutesBeforeService = detailsServices
                    .slice(0, index)
                    .reduce((total, previousService) => total + previousService.durationMinutes, 0);
                  const serviceStart = addMinutesToTimeLabel(detailsBooking.starts_at, minutesBeforeService);
                  const serviceEnd = addMinutesToTimeLabel(detailsBooking.starts_at, minutesBeforeService + service.durationMinutes);

                  return (
                    <section key={`${service.name}-${index}`} className={styles.detailServiceCard}>
                      <div><span>Услуга</span><strong>{service.name}</strong></div>
                      <div>
                        <span>Стоимость услуги</span>
                        <strong>
                          {service.price == null ? (
                            "-"
                          ) : service.discountPercent > 0 ? (
                            <>
                              <s className={styles.oldPrice}>{`${service.price.toLocaleString("ru-RU")} т`}</s>
                              {`${Math.round(service.price * (1 - service.discountPercent / 100)).toLocaleString("ru-RU")} т`}
                            </>
                          ) : (
                            `${service.price.toLocaleString("ru-RU")} т`
                          )}
                        </strong>
                      </div>
                      <div><span>Дата и время</span><strong>{`${formatDateTitle(new Date(detailsBooking.starts_at))}, ${serviceStart} - ${serviceEnd}`}</strong></div>
                      <div>
                        <span>Ресурс</span>
                        <strong className={styles.resourceValue}>
                          <b>
                            {detailsSpecialist?.photo_url ? (
                              <img src={detailsSpecialist.photo_url} alt="" />
                            ) : (
                              detailsSpecialist?.full_name.slice(0, 1).toUpperCase() || "С"
                            )}
                          </b>
                          {detailsBooking.manager_name || "Не назначен"}
                        </strong>
                      </div>
                      <div><span>Статус</span><strong className={styles[`detailStatus${getStatusTone(detailsBooking.status).charAt(0).toUpperCase()}${getStatusTone(detailsBooking.status).slice(1)}`]}>{getStatusLabel(detailsBooking.status)}</strong></div>
                    </section>
                  );
                })}
              </div>

              <div className={styles.totalRow}>
                <span>Общая сумма</span>
                {(() => {
                  const total = detailsServices.reduce((sum, service) => sum + (service.price || 0), 0);
                  const discountedTotal = Math.round(
                    detailsServices.reduce((sum, service) => sum + (service.price || 0) * (1 - service.discountPercent / 100), 0),
                  );

                  return discountedTotal < total ? (
                    <strong className={styles.totalWithDiscount}>
                      <b>{`${discountedTotal.toLocaleString("ru-RU")} т`}</b>
                      <s>{`${total.toLocaleString("ru-RU")} т`}</s>
                    </strong>
                  ) : (
                    <strong>{`${total.toLocaleString("ru-RU")} т`}</strong>
                  );
                })()}
              </div>
              <div className={styles.commentBlock}>
                <span>Комментарий</span>
                <p>Комментарий не добавлен</p>
              </div>
            </div>

            <footer className={styles.detailsFooter}>
              <button type="button" className={styles.dangerButton} onClick={() => void updateBookingStatus("no_show")} disabled={isUpdatingStatus}>
                Неявка
              </button>
              <button type="button" className={styles.completeButton} onClick={() => void updateBookingStatus("completed")} disabled={isUpdatingStatus}>
                {isUpdatingStatus ? "Сохранение..." : "Оплачен"}
              </button>
            </footer>
          </section>
        </div>
      ) : null}

      {isDeleteConfirmOpen && detailsBooking ? (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Удаление записи">
          <section className={styles.confirmModal}>
            <h3>Удалить запись?</h3>
            <p>Вы точно хотите удалить? Запись будет удалена полностью, восстановить её не получится.</p>
            <div className={styles.confirmActions}>
              <button type="button" className={styles.noShowButton} onClick={() => setIsDeleteConfirmOpen(false)} disabled={isDeletingBooking}>
                Отменить
              </button>
              <button type="button" className={styles.dangerButton} onClick={() => void deleteBooking()} disabled={isDeletingBooking}>
                {isDeletingBooking ? "Удаление..." : "Удалить"}
              </button>
            </div>
          </section>
        </div>
      ) : null}

      {isBulkScheduleOpen ? (
        <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-label="Составить график работы">
          <section className={styles.bulkScheduleModal}>
            <header className={styles.bulkScheduleHeader}>
              <div className={styles.detailsTitle}>
                <img src="/setting.svg" alt="" aria-hidden />
                <h3>Составить график работы</h3>
              </div>
              <button type="button" className={styles.closeModalButton} onClick={() => setIsBulkScheduleOpen(false)} aria-label="Закрыть">×</button>
            </header>
            <div className={styles.bulkScheduleBody}>
              <label className={styles.scheduleSpecialistSelect}><span>Выберите специалиста</span><select value={scheduleSpecialistId} onChange={(event) => changeScheduleSpecialist(event.target.value)}>{activeSpecialists.map((specialist) => <option key={specialist.id} value={String(specialist.id)}>{specialist.full_name}</option>)}</select></label>
              <div className={styles.scheduleEditorLayout}>
                <section className={styles.scheduleCalendar}>
                  <header className={styles.scheduleCalendarHeader}><button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() - 1, 1))} aria-label="Предыдущий месяц">‹</button><strong>{`${RUS_MONTH[calendarMonth.getMonth()]} ${calendarMonth.getFullYear()}`}</strong><button type="button" onClick={() => setCalendarMonth((month) => new Date(month.getFullYear(), month.getMonth() + 1, 1))} aria-label="Следующий месяц">›</button></header>
                  <div className={styles.calendarWeekdays}>{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => <span key={day}>{day}</span>)}</div>
                  <div className={styles.scheduleCalendarDays}>{calendarDays.map((date) => { const day = getScheduleForDate(bulkScheduleDraft, date); const dateKey = formatDateInputValue(date); const isSelected = selectedScheduleDateKeys.includes(dateKey); return <button key={dateKey} type="button" className={`${styles.scheduleCalendarDay} ${date.getMonth() === calendarMonth.getMonth() ? "" : styles.calendarDayMuted} ${isSelected ? styles.scheduleCalendarDaySelected : ""}`} onClick={() => toggleScheduleDate(date)}><span>{date.getDate()}</span><i className={day?.is_day_off ? styles.dayOffDot : styles.workingDayDot} /></button>; })}</div>
                  <p className={styles.scheduleLegend}><span><i className={styles.workingDayDot} />Рабочий день</span><span><i className={styles.dayOffDot} />Выходной</span></p>
                  {bulkScheduleError ? <p className={styles.scheduleFormError}>{bulkScheduleError}</p> : null}
                </section>
                {(() => { const day = getScheduleForDate(bulkScheduleDraft, selectedDate); if (!day) return null; return <section className={styles.scheduleDayEditor}><section className={styles.scheduleSettingsPanel}><div className={styles.scheduleDayStatus}><span>{selectedScheduleDateKeys.length > 1 ? `Выбрано дней: ${selectedScheduleDateKeys.length}` : formatDateTitle(selectedDate)}</span><b className={day.is_day_off ? styles.dayOffStatus : styles.workingStatus}>{day.is_day_off ? "Выходной" : "Рабочий"}</b><button type="button" className={day.is_day_off ? styles.makeWorkingButton : styles.makeDayOffButton} onClick={() => toggleSelectedDayOff(day)}>{day.is_day_off ? "Сделать рабочим" : "Сделать выходным"}</button></div></section>
                  {!day.is_day_off ? <><section className={`${styles.scheduleTimeSection} ${styles.scheduleSettingsPanel}`}><h4>Рабочие часы</h4><label>Начало работы<input type="time" value={day.start_time} onChange={(event) => updateSelectedScheduleDays({ start_time: event.target.value })} /></label><label>Окончание работы<input type="time" value={day.end_time} onChange={(event) => updateSelectedScheduleDays({ end_time: event.target.value })} /></label></section><section className={`${styles.scheduleTimeSection} ${styles.scheduleSettingsPanel}`}><h4>Доступное время для услуг со скидкой</h4><label>Начало<input type="time" value={day.discount_start} onChange={(event) => updateSelectedScheduleDays({ discount_start: event.target.value })} /></label><label>Окончание<input type="time" value={day.discount_end} onChange={(event) => updateSelectedScheduleDays({ discount_end: event.target.value })} /></label></section><section className={`${styles.scheduleTimeSection} ${styles.scheduleSettingsPanel}`}><div className={styles.breakTitle}><h4>Перерывы</h4><button type="button" onClick={() => updateSelectedScheduleDays({ breaks: [...day.breaks, { name: "Перерыв", start_time: "15:00", end_time: "15:30" }] })} aria-label="Добавить перерыв">+</button></div>{day.breaks.map((scheduleBreak, index) => <div className={styles.breakRow} key={`${scheduleBreak.name}-${index}`}><input value={scheduleBreak.name} onChange={(event) => updateSelectedScheduleDays({ breaks: day.breaks.map((item, itemIndex) => itemIndex === index ? { ...item, name: event.target.value } : item) })} /><input type="time" value={scheduleBreak.start_time} onChange={(event) => updateSelectedScheduleDays({ breaks: day.breaks.map((item, itemIndex) => itemIndex === index ? { ...item, start_time: event.target.value } : item) })} /><input type="time" value={scheduleBreak.end_time} onChange={(event) => updateSelectedScheduleDays({ breaks: day.breaks.map((item, itemIndex) => itemIndex === index ? { ...item, end_time: event.target.value } : item) })} /><button type="button" onClick={() => updateSelectedScheduleDays({ breaks: day.breaks.filter((_, itemIndex) => itemIndex !== index) })} aria-label="Удалить перерыв">×</button></div>)}</section></> : <p className={`${styles.dayOffNotice} ${styles.scheduleSettingsPanel}`}>Для выходного дня запись недоступна.</p>}</section>; })()}
              </div>
            </div>
            <footer className={styles.bulkScheduleFooter}>
              <button type="button" className={styles.noShowButton} onClick={() => setIsBulkScheduleOpen(false)}>Отменить</button>
              <button type="button" className={styles.completeButton} onClick={() => void submitBulkSchedule()} disabled={isSavingBulkSchedule}>{isSavingBulkSchedule ? "Сохранение..." : "Применить график"}</button>
            </footer>
          </section>
        </div>
      ) : null}
    </section>
  );
}
