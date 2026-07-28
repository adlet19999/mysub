"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";
import { compressImageFileToDataUrl } from "../../../../lib/imageCompression";

type Service = {
  id: number;
  name: string;
  category_name: string;
  kind_name: string | null;
  is_active: boolean;
};
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
  description: string;
  phone: string;
  email: string;
  photo_url: string;
  working_schedule: WorkingDaySchedule[];
  service_ids: number[];
  service_names: string[];
  is_active: boolean;
};

type SpecialistPhotoPayload = {
  photo_url?: string;
};

type SpecialistFormState = {
  fullName: string;
  description: string;
  pendingServiceId: string;
  selectedServiceIds: number[];
  photoBase64: string;
};

type ModalMode = "create" | "edit";
type ToastTone = "success" | "error";
type ToastState = { text: string; tone: ToastTone };
type SchedulePresetKey = "standard" | "weekend-off" | "copy-weekdays";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
const WEEK_DAYS: { key: WorkingDayKey; label: string }[] = [
  { key: "mon", label: "Понедельник" },
  { key: "tue", label: "Вторник" },
  { key: "wed", label: "Среда" },
  { key: "thu", label: "Четверг" },
  { key: "fri", label: "Пятница" },
  { key: "sat", label: "Суббота" },
  { key: "sun", label: "Воскресенье" },
];
function defaultWorkingSchedule(): WorkingDaySchedule[] {
  return WEEK_DAYS.map((item) => {
    const isWeekend = item.key === "sat" || item.key === "sun";
    return {
      day: item.key,
      is_day_off: isWeekend,
      start_time: "09:00",
      end_time: "18:00",
      break_start: "13:00",
      break_end: "14:00",
    };
  });
}

function isDayKey(value: string): value is WorkingDayKey {
  return value === "mon" || value === "tue" || value === "wed" || value === "thu" || value === "fri" || value === "sat" || value === "sun";
}

function normalizeWorkingSchedule(raw: unknown): WorkingDaySchedule[] {
  const fallback = defaultWorkingSchedule();
  if (!Array.isArray(raw)) {
    return fallback;
  }

  const map = new Map<WorkingDayKey, WorkingDaySchedule>();
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") {
      continue;
    }
    const row = entry as Partial<WorkingDaySchedule> & { day?: string };
    if (!row.day || !isDayKey(row.day)) {
      continue;
    }

    map.set(row.day, {
      day: row.day,
      is_day_off: Boolean(row.is_day_off),
      start_time: typeof row.start_time === "string" ? row.start_time : "09:00",
      end_time: typeof row.end_time === "string" ? row.end_time : "18:00",
      break_start: typeof row.break_start === "string" ? row.break_start : "13:00",
      break_end: typeof row.break_end === "string" ? row.break_end : "14:00",
    });
  }

  return WEEK_DAYS.map((item) => map.get(item.key) ?? fallback.find((day) => day.day === item.key)!).filter(Boolean);
}

export default function SpecialistsPage() {
  const tenant = TENANT_DEFAULT;
  const [partnerEmail, setPartnerEmail] = useState("");
  const [authResolved, setAuthResolved] = useState(false);

  const [services, setServices] = useState<Service[]>([]);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [specialistPhotos, setSpecialistPhotos] = useState<Record<number, string>>({});

  const [searchQuery, setSearchQuery] = useState("");
  const [tab, setTab] = useState<"active" | "archived" | "all">("active");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isBulkScheduleOpen, setIsBulkScheduleOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<Specialist | null>(null);
  const [scheduleTarget, setScheduleTarget] = useState<Specialist | null>(null);
  const [scheduleDraft, setScheduleDraft] = useState<WorkingDaySchedule[]>(defaultWorkingSchedule());
  const [activeSchedulePreset, setActiveSchedulePreset] = useState<SchedulePresetKey | null>(null);
  const [bulkScheduleDraft, setBulkScheduleDraft] = useState<WorkingDaySchedule[]>(defaultWorkingSchedule());
  const [activeBulkSchedulePreset, setActiveBulkSchedulePreset] = useState<SchedulePresetKey | null>(null);
  const [bulkSelectedSpecialistIds, setBulkSelectedSpecialistIds] = useState<number[]>([]);
  const [modalMode, setModalMode] = useState<ModalMode>("create");
  const [editingSpecialist, setEditingSpecialist] = useState<Specialist | null>(null);
  const [kindError, setKindError] = useState("");
  const [formError, setFormError] = useState("");
  const [scheduleError, setScheduleError] = useState("");
  const [form, setForm] = useState<SpecialistFormState>({
    fullName: "",
    description: "",
    pendingServiceId: "",
    selectedServiceIds: [],
    photoBase64: "",
  });
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadingPhotoIdsRef = useRef<Set<number>>(new Set());

  function showToast(text: string, tone: ToastTone = "success") {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    setToast({ text, tone });
    toastTimerRef.current = setTimeout(() => setToast(null), 2200);
  }

  const availableServices = useMemo(() => {
    return services.filter((item) => item.is_active).sort((left, right) => left.name.localeCompare(right.name));
  }, [services]);

  const visibleSpecialists = useMemo(() => {
    const text = searchQuery.trim().toLowerCase();
    return specialists
      .filter((item) => {
        if (tab === "all") {
          return true;
        }
        return tab === "active" ? item.is_active : !item.is_active;
      })
      .filter((item) => {
        if (!text) {
          return true;
        }
        return (
          item.full_name.toLowerCase().includes(text) ||
          item.description.toLowerCase().includes(text) ||
          item.phone.toLowerCase().includes(text) ||
          item.email.toLowerCase().includes(text)
        );
      });
  }, [searchQuery, specialists, tab]);

  const activeSpecialists = useMemo(() => {
    return specialists.filter((item) => item.is_active).sort((left, right) => left.full_name.localeCompare(right.full_name));
  }, [specialists]);

  async function api(path: string, init?: RequestInit) {
    return fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Tenant": tenant,
        ...(partnerEmail ? { "X-Partner-Email": partnerEmail } : {}),
        ...(init?.headers ?? {}),
      },
    });
  }

  async function loadData() {
    if (!partnerEmail) {
      return;
    }

    try {
      const [servicesRes, specialistsRes] = await Promise.all([
        api("/partner/services/?include_image=0"),
        api("/partner/specialists/?include_schedule=0"),
      ]);

      if (!servicesRes.ok || !specialistsRes.ok) {
        return;
      }

      const servicesPayload = (await servicesRes.json()) as Service[];
      const specialistsPayload = (await specialistsRes.json()) as Specialist[];

      setServices(Array.isArray(servicesPayload) ? servicesPayload : []);
      setSpecialists(
        Array.isArray(specialistsPayload)
          ? specialistsPayload.map((item) => ({ ...item, working_schedule: normalizeWorkingSchedule(item.working_schedule) }))
          : [],
      );
    } catch {
      // Keep this dashboard resilient to temporary API connectivity issues.
    }
  }

  async function preloadSpecialistPhotos(specialistIds: number[]) {
    const idsToLoad = specialistIds.filter(
      (id) =>
        !specialistPhotos[id] &&
        !specialists.find((specialist) => specialist.id === id)?.photo_url &&
        !loadingPhotoIdsRef.current.has(id),
    );
    if (!idsToLoad.length) {
      return;
    }

    idsToLoad.forEach((id) => loadingPhotoIdsRef.current.add(id));

    try {
      const results = await Promise.all(
        idsToLoad.map(async (id) => {
          const response = await api(`/partner/specialists/${id}/`);
          if (!response.ok) {
            return { id, photo: "" };
          }
          const payload = (await response.json()) as SpecialistPhotoPayload;
          return { id, photo: (payload.photo_url || "").trim() };
        }),
      );

      setSpecialistPhotos((prev) => {
        const next = { ...prev };
        for (const item of results) {
          if (item.photo) {
            next[item.id] = item.photo;
          }
        }
        return next;
      });
    } finally {
      idsToLoad.forEach((id) => loadingPhotoIdsRef.current.delete(id));
    }
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
    } finally {
      setAuthResolved(true);
    }
  }, []);

  useEffect(() => {
    if (!authResolved) {
      return;
    }
    void loadData();
  }, [authResolved, partnerEmail]);

  useEffect(() => {
    const visibleIds = visibleSpecialists.slice(0, 8).map((item) => item.id);
    if (!visibleIds.length) {
      return;
    }
    void preloadSpecialistPhotos(visibleIds);
  }, [visibleSpecialists]);

  function openCreateModal() {
    setModalMode("create");
    setEditingSpecialist(null);
    setKindError("");
    setFormError("");
    setForm({
      fullName: "",
      description: "",
      pendingServiceId: availableServices[0] ? String(availableServices[0].id) : "",
      selectedServiceIds: [],
      photoBase64: "",
    });
    setIsModalOpen(true);
  }

  function openEditModal(specialist: Specialist) {
    const specialistPhoto = specialistPhotos[specialist.id] || specialist.photo_url || "";
    setModalMode("edit");
    setEditingSpecialist(specialist);
    setKindError("");
    setFormError("");
    setForm({
      fullName: specialist.full_name,
      description: specialist.description || "",
      pendingServiceId: availableServices[0] ? String(availableServices[0].id) : "",
      selectedServiceIds: specialist.service_ids,
      photoBase64: specialistPhoto,
    });
    setIsModalOpen(true);

    if (!specialistPhoto) {
      void preloadSpecialistPhotos([specialist.id]);
    }
  }

  async function openScheduleModal(specialist: Specialist) {
    setScheduleTarget(specialist);
    setScheduleDraft(normalizeWorkingSchedule(specialist.working_schedule));
    setActiveSchedulePreset(null);
    setScheduleError("");

    try {
      const response = await api(`/partner/specialists/${specialist.id}/`);
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as Pick<Specialist, "working_schedule">;
      setScheduleDraft(normalizeWorkingSchedule(payload.working_schedule));
    } catch {
      setScheduleError("Не удалось загрузить текущий график");
    }
  }

  function closeScheduleModal() {
    setScheduleTarget(null);
    setActiveSchedulePreset(null);
    setScheduleError("");
  }

  function openBulkScheduleModal() {
    const activeIds = activeSpecialists.map((item) => item.id);
    setIsBulkScheduleOpen(true);
    setBulkScheduleDraft(defaultWorkingSchedule());
    setActiveBulkSchedulePreset(null);
    setBulkSelectedSpecialistIds(activeIds);
    setScheduleError("");
  }

  function closeBulkScheduleModal() {
    setIsBulkScheduleOpen(false);
    setActiveBulkSchedulePreset(null);
    setScheduleError("");
  }

  function toggleBulkSpecialistSelection(specialistId: number) {
    setBulkSelectedSpecialistIds((prev) =>
      prev.includes(specialistId) ? prev.filter((id) => id !== specialistId) : [...prev, specialistId],
    );
  }

  function toggleBulkSelectAll(checked: boolean) {
    if (!checked) {
      setBulkSelectedSpecialistIds([]);
      return;
    }
    setBulkSelectedSpecialistIds(activeSpecialists.map((item) => item.id));
  }

  function updateDaySchedule(day: WorkingDayKey, patch: Partial<WorkingDaySchedule>) {
    setScheduleError("");
    setActiveSchedulePreset(null);
    setScheduleDraft((prev) => prev.map((row) => (row.day === day ? { ...row, ...patch } : row)));
  }

  function updateBulkDaySchedule(day: WorkingDayKey, patch: Partial<WorkingDaySchedule>) {
    setScheduleError("");
    setActiveBulkSchedulePreset(null);
    setBulkScheduleDraft((prev) => prev.map((row) => (row.day === day ? { ...row, ...patch } : row)));
  }

  function copyDayToWeekdays(sourceDay: WorkingDayKey) {
    const source = scheduleDraft.find((item) => item.day === sourceDay);
    if (!source) {
      return;
    }
    const weekdays: WorkingDayKey[] = ["mon", "tue", "wed", "thu", "fri"];
    setScheduleError("");
    setActiveSchedulePreset("copy-weekdays");
    setScheduleDraft((prev) =>
      prev.map((row) => {
        if (!weekdays.includes(row.day)) {
          return row;
        }
        return {
          ...row,
          is_day_off: source.is_day_off,
          start_time: source.start_time,
          end_time: source.end_time,
          break_start: source.break_start,
          break_end: source.break_end,
        };
      }),
    );
  }

  function copyBulkDayToWeekdays(sourceDay: WorkingDayKey) {
    const source = bulkScheduleDraft.find((item) => item.day === sourceDay);
    if (!source) {
      return;
    }
    const weekdays: WorkingDayKey[] = ["mon", "tue", "wed", "thu", "fri"];
    setScheduleError("");
    setActiveBulkSchedulePreset("copy-weekdays");
    setBulkScheduleDraft((prev) =>
      prev.map((row) => {
        if (!weekdays.includes(row.day)) {
          return row;
        }
        return {
          ...row,
          is_day_off: source.is_day_off,
          start_time: source.start_time,
          end_time: source.end_time,
          break_start: source.break_start,
          break_end: source.break_end,
        };
      }),
    );
  }

  function applyTemplate(mode: "standard" | "weekend-off") {
    setScheduleError("");
    setActiveSchedulePreset(mode);
    setScheduleDraft((prev) =>
      prev.map((row) => {
        if (mode === "standard") {
          const isWeekend = row.day === "sat" || row.day === "sun";
          return {
            ...row,
            is_day_off: isWeekend,
            start_time: "09:00",
            end_time: "18:00",
            break_start: "13:00",
            break_end: "14:00",
          };
        }

        const isWeekend = row.day === "sat" || row.day === "sun";
        if (isWeekend) {
          return {
            ...row,
            is_day_off: true,
            start_time: "",
            end_time: "",
            break_start: "",
            break_end: "",
          };
        }
        return row;
      }),
    );
  }

  function applyBulkTemplate(mode: "standard" | "weekend-off") {
    setScheduleError("");
    setActiveBulkSchedulePreset(mode);
    setBulkScheduleDraft((prev) =>
      prev.map((row) => {
        if (mode === "standard") {
          const isWeekend = row.day === "sat" || row.day === "sun";
          return {
            ...row,
            is_day_off: isWeekend,
            start_time: "09:00",
            end_time: "18:00",
            break_start: "13:00",
            break_end: "14:00",
          };
        }

        const isWeekend = row.day === "sat" || row.day === "sun";
        if (isWeekend) {
          return {
            ...row,
            is_day_off: true,
            start_time: "",
            end_time: "",
            break_start: "",
            break_end: "",
          };
        }
        return row;
      }),
    );
  }

  function validateSchedule(rows: WorkingDaySchedule[]) {
    for (const row of rows) {
      if (row.is_day_off) {
        continue;
      }
      if (!row.start_time || !row.end_time) {
        return `Укажите время начала и конца для дня ${WEEK_DAYS.find((item) => item.key === row.day)?.label || row.day}`;
      }
      if (row.start_time >= row.end_time) {
        return `Время начала должно быть раньше времени окончания (${WEEK_DAYS.find((item) => item.key === row.day)?.label || row.day})`;
      }

      const hasBreakStart = Boolean(row.break_start);
      const hasBreakEnd = Boolean(row.break_end);
      if (hasBreakStart !== hasBreakEnd) {
        return `Для перерыва заполните оба поля (${WEEK_DAYS.find((item) => item.key === row.day)?.label || row.day})`;
      }

      if (hasBreakStart && hasBreakEnd) {
        if (!(row.start_time < row.break_start && row.break_start < row.break_end && row.break_end < row.end_time)) {
          return `Перерыв должен быть внутри рабочего времени (${WEEK_DAYS.find((item) => item.key === row.day)?.label || row.day})`;
        }
      }
    }

    return "";
  }

  function addService() {
    const selectedId = Number(form.pendingServiceId);
    if (!selectedId || form.selectedServiceIds.includes(selectedId)) {
      return;
    }
    setKindError("");
    setForm((prev) => ({ ...prev, selectedServiceIds: [...prev.selectedServiceIds, selectedId] }));
  }

  function removeService(serviceId: number) {
    setForm((prev) => {
      const nextSelected = prev.selectedServiceIds.filter((item) => item !== serviceId);
      if (nextSelected.length) {
        setKindError("");
      }
      return { ...prev, selectedServiceIds: nextSelected };
    });
  }

  async function onSelectPhoto(file: File | null) {
    if (!file) {
      return;
    }
    try {
      const result = await compressImageFileToDataUrl(file);
      setForm((prev) => ({ ...prev, photoBase64: result }));
    } catch {
      showToast("Не удалось обработать фото", "error");
    }
  }

  function clearPhoto() {
    setForm((prev) => ({ ...prev, photoBase64: "" }));
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
  }

  async function submitSpecialist(event: FormEvent) {
    event.preventDefault();

    setFormError("");

    if (!form.fullName.trim()) {
      return;
    }

    if (!form.selectedServiceIds.length) {
      setKindError("Выберите хотя бы одну созданную услугу");
      return;
    }

    setKindError("");

    try {
      const response = await api(
        modalMode === "create" || !editingSpecialist
          ? "/partner/specialists/"
          : `/partner/specialists/${editingSpecialist.id}/`,
        {
          method: modalMode === "create" || !editingSpecialist ? "POST" : "PATCH",
          body: JSON.stringify({
            full_name: form.fullName,
            description: form.description,
            phone: "",
            email: "",
            ...(form.photoBase64.startsWith("data:") ? { photo_base64: form.photoBase64 } : {}),
            service_ids: form.selectedServiceIds,
            is_active: true,
          }),
        },
      );
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { message?: string } | null;
        setFormError(payload?.message || "Не удалось сохранить специалиста");
        return;
      }

      setIsModalOpen(false);
      await loadData();
      showToast(modalMode === "create" ? "Специалист успешно добавлен" : "Специалист успешно обновлен", "success");
    } catch {
      setFormError("Не удалось связаться с сервером. Повторите попытку.");
      return;
    }
  }

  function openArchiveModal(specialist: Specialist) {
    setArchiveTarget(specialist);
  }

  async function submitArchiveDecision() {
    if (!archiveTarget) {
      return;
    }

    const response = await api(`/partner/specialists/${archiveTarget.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !archiveTarget.is_active }),
    });
    if (!response.ok) {
      return;
    }

    setArchiveTarget(null);
    await loadData();
    showToast(
      !archiveTarget.is_active ? "Специалист разархивирован" : "Специалист перенесен в архив",
      !archiveTarget.is_active ? "success" : "error",
    );
  }

  async function submitSchedule() {
    if (!scheduleTarget) {
      return;
    }

    const scheduleValidationError = validateSchedule(scheduleDraft);
    if (scheduleValidationError) {
      setScheduleError(scheduleValidationError);
      return;
    }

    const response = await api(`/partner/specialists/${scheduleTarget.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ working_schedule: scheduleDraft }),
    });
    if (!response.ok) {
      setScheduleError("Не удалось сохранить график");
      return;
    }

    closeScheduleModal();
    await loadData();
    showToast("График работы сохранен", "success");
  }

  async function submitBulkSchedule() {
    if (!bulkSelectedSpecialistIds.length) {
      setScheduleError("Выберите хотя бы одного специалиста");
      return;
    }

    const scheduleValidationError = validateSchedule(bulkScheduleDraft);
    if (scheduleValidationError) {
      setScheduleError(scheduleValidationError);
      return;
    }

    const results = await Promise.all(
      bulkSelectedSpecialistIds.map(async (specialistId) => {
        const response = await api(`/partner/specialists/${specialistId}/`, {
          method: "PATCH",
          body: JSON.stringify({ working_schedule: bulkScheduleDraft }),
        });
        return response.ok;
      }),
    );

    const successCount = results.filter(Boolean).length;
    if (!successCount) {
      setScheduleError("Не удалось сохранить график");
      return;
    }

    closeBulkScheduleModal();
    await loadData();
    if (successCount === bulkSelectedSpecialistIds.length) {
      showToast(`График применен к ${successCount} специалистам`, "success");
    } else {
      showToast(`График применен к ${successCount} из ${bulkSelectedSpecialistIds.length}`, "error");
    }
  }

  return (
    <>
      <main className={styles.page}>
        <section className={styles.block}>
          {toast ? (
            <div
              className={`${styles.toast} ${toast.tone === "error" ? styles.toastError : styles.toastSuccess}`}
              role="status"
              aria-live="polite"
            >
              <span className={`${styles.toastIcon} ${toast.tone === "error" ? styles.toastIconError : styles.toastIconSuccess}`} aria-hidden>
                {toast.tone === "error" ? "" : "✓"}
              </span>
              <div className={styles.toastContent}>
                <strong>{toast.text}</strong>
              </div>
              <button
                type="button"
                className={styles.toastClose}
                onClick={() => setToast(null)}
                aria-label="Закрыть уведомление"
              >
                ×
              </button>
            </div>
          ) : null}

          <div className={styles.blockHeadRow}>
            <div className={styles.headText}>
              <h1>Специалисты и ресурсы</h1>
              <p>Управление рабочими местами и помещениями</p>
            </div>

            <div className={styles.headActions}>
              <button
                type="button"
                className={styles.scheduleTopButton}
                onClick={openBulkScheduleModal}
                disabled={!partnerEmail || !activeSpecialists.length}
              >
                <img src="/setting.svg" alt="" className={styles.actionIcon} aria-hidden />
                Составить график работы
              </button>

              <button type="button" className={styles.addButton} onClick={openCreateModal} disabled={!partnerEmail}>
                <span className={styles.plusIcon} aria-hidden>+</span>
                Добавить специалиста
              </button>
            </div>
          </div>

          <div className={styles.filterRow}>
            <button
              type="button"
              className={tab === "active" ? styles.pillActive : styles.pill}
              onClick={() => setTab("active")}
            >
              Активные({specialists.filter((item) => item.is_active).length})
            </button>
            <button
              type="button"
              className={tab === "archived" ? styles.pillActive : styles.pill}
              onClick={() => setTab("archived")}
            >
              Архивные({specialists.filter((item) => !item.is_active).length})
            </button>
            <button type="button" className={tab === "all" ? styles.pillActive : styles.pill} onClick={() => setTab("all")}>
              Все
            </button>
          </div>

          {authResolved && !partnerEmail ? (
            <p className={styles.error}>Не удалось определить текущего партнера. Выйдите и войдите снова.</p>
          ) : null}

          <div className={styles.cardsGrid}>
            {visibleSpecialists.map((specialist) => (
              <article key={specialist.id} className={styles.card}>
                <div className={styles.cardTopRow}>
                  <h3>{specialist.full_name}</h3>
                  <span className={specialist.is_active ? styles.statusActive : styles.statusArchived}>
                    {specialist.is_active ? "Активна" : "Архив"}
                  </span>
                </div>

                {(specialistPhotos[specialist.id] || specialist.photo_url) ? (
                  <img
                    src={specialistPhotos[specialist.id] || specialist.photo_url}
                    alt=""
                    className={styles.cardPhoto}
                    loading="lazy"
                    decoding="async"
                  />
                ) : (
                  <div className={styles.previewStub} />
                )}

                <p className={styles.cardDesc}>
                  {specialist.description.trim() || "Описание не указано"}
                </p>

                <div className={styles.cardActions}>
                  <button type="button" className={styles.editButton} onClick={() => openEditModal(specialist)}>
                    <img src="/change.svg" alt="" className={styles.actionIcon} aria-hidden />
                    Изменить
                  </button>
                  <button type="button" className={styles.archiveButton} onClick={() => openArchiveModal(specialist)}>
                    <img src="/Archieve.svg" alt="" className={styles.actionIcon} aria-hidden />
                  </button>
                </div>
              </article>
            ))}

            {!visibleSpecialists.length ? <p className={styles.empty}>Нет специалистов</p> : null}
          </div>
        </section>
      </main>

      {isModalOpen ? (
        <div className={styles.overlay}>
          <form className={styles.modal} onSubmit={submitSpecialist}>
            <header className={styles.modalHeader}>
              <div className={styles.modalTitleWrap}>
                <img src="/modal_icon.svg" alt="" className={styles.modalIcon} aria-hidden />
                <h2>{modalMode === "create" ? "Добавить специалиста" : "Редактировать специалиста"}</h2>
              </div>
              <button type="button" className={styles.close} onClick={() => setIsModalOpen(false)}>
                ×
              </button>
            </header>

            <div className={styles.modalBody}>
              <label>
                ФИО
                <input
                  value={form.fullName}
                  onChange={(event) => setForm((prev) => ({ ...prev, fullName: event.target.value }))}
                  placeholder="Иванов Иван"
                  required
                />
              </label>

              <label>
                Описание
                <textarea
                  value={form.description}
                  onChange={(event) => setForm((prev) => ({ ...prev, description: event.target.value }))}
                  placeholder="Кратко опишите специализацию и опыт"
                  rows={5}
                />
              </label>

              <label>
                Услуга
                <div className={styles.kindPickerRow}>
                  <select
                    value={form.pendingServiceId}
                    onChange={(event) => setForm((prev) => ({ ...prev, pendingServiceId: event.target.value }))}
                    required={!form.selectedServiceIds.length}
                  >
                    <option value="" disabled>Выберите созданную услугу</option>
                    {availableServices.map((service) => (
                      <option key={service.id} value={service.id}>
                        {service.name}
                      </option>
                    ))}
                  </select>
                  <button type="button" className={styles.addKindButton} onClick={addService}>
                    Добавить
                  </button>
                </div>
                <div className={styles.kindChips}>
                  {form.selectedServiceIds.map((serviceId) => {
                    const service = availableServices.find((item) => item.id === serviceId);
                    if (!service) {
                      return null;
                    }
                    return (
                      <button
                        key={service.id}
                        type="button"
                        className={styles.kindChip}
                        onClick={() => removeService(service.id)}
                        title="Удалить"
                      >
                        {service.name}
                        <span aria-hidden>×</span>
                      </button>
                    );
                  })}
                </div>
                {kindError ? <p className={styles.kindError}>{kindError}</p> : null}
              </label>

              {formError ? <p className={styles.error}>{formError}</p> : null}

              <label className={styles.photoField}>
                Фото специалиста
                {form.photoBase64 ? (
                  <div className={styles.photoPreviewBlock}>
                    <img src={form.photoBase64} alt="" className={styles.modalPhotoPreview} />
                    <button type="button" className={styles.removePhotoIconButton} onClick={clearPhoto} aria-label="Удалить фото">
                      <img src="/delete.svg" alt="" className={styles.removePhotoIcon} aria-hidden />
                    </button>
                  </div>
                ) : (
                  <div className={styles.photoDropzone}>
                    <input
                      ref={photoInputRef}
                      type="file"
                      accept="image/*"
                      onChange={(event) => onSelectPhoto(event.target.files?.[0] ?? null)}
                    />
                    <img src="/photo.svg" alt="" className={styles.photoDropzoneIcon} aria-hidden />
                    <span>Добавить фото</span>
                  </div>
                )}
              </label>
            </div>

            <footer className={styles.modalFooter}>
              <button type="button" className={styles.cancelButton} onClick={() => setIsModalOpen(false)}>
                Отменить
              </button>
              <button type="submit" className={styles.saveButton}>{modalMode === "create" ? "Создать" : "Сохранить"}</button>
            </footer>
          </form>
        </div>
      ) : null}

      {archiveTarget ? (
        <div className={styles.overlay}>
          <div className={styles.statusModal}>
            <div className={styles.statusBody}>
              <div className={styles.statusIconWrap}>
                <img src="/Archieve.svg" alt="" className={styles.statusIconImage} aria-hidden />
              </div>
              <div className={styles.statusTextBlock}>
                <h3>{archiveTarget.is_active ? "Архивировать специалиста" : "Разархивировать специалиста"}</h3>
                <p>
                  Вы уверены, что хотите {archiveTarget.is_active ? "архивировать" : "разархивировать"} “
                  <strong>{archiveTarget.full_name}</strong>” ?
                </p>
              </div>
            </div>

            <div className={styles.statusActions}>
              <button type="button" className={styles.statusCancelButton} onClick={() => setArchiveTarget(null)}>
                Отменить
              </button>
              <button type="button" className={styles.statusWarningButton} onClick={() => void submitArchiveDecision()}>
                {archiveTarget.is_active ? "Архивировать" : "Разархивировать"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {scheduleTarget ? (
        <div className={styles.overlay}>
          <div className={styles.modal}>
            <header className={styles.modalHeader}>
              <div className={styles.modalTitleWrap}>
                <img src="/setting.svg" alt="" className={styles.modalIcon} aria-hidden />
                <h2>График работы специалиста</h2>
              </div>
              <button type="button" className={styles.close} onClick={closeScheduleModal}>
                ×
              </button>
            </header>

            <div className={styles.modalBody}>
              <p className={styles.scheduleTarget}>Специалист: <strong>{scheduleTarget.full_name}</strong></p>

              <div className={styles.scheduleTools}>
                <button
                  type="button"
                  className={activeSchedulePreset === "standard" ? styles.scheduleToolActive : undefined}
                  onClick={() => applyTemplate("standard")}
                >
                  Шаблон 09:00-18:00
                </button>
                <button
                  type="button"
                  className={activeSchedulePreset === "weekend-off" ? styles.scheduleToolActive : undefined}
                  onClick={() => applyTemplate("weekend-off")}
                >
                  Выходные: Сб/Вс
                </button>
                <button
                  type="button"
                  className={activeSchedulePreset === "copy-weekdays" ? styles.scheduleToolActive : undefined}
                  onClick={() => copyDayToWeekdays("mon")}
                >
                  Копировать Пн на Пн-Пт
                </button>
              </div>

              {scheduleError ? <p className={styles.scheduleError}>{scheduleError}</p> : null}

              <div className={styles.scheduleGrid}>
                {scheduleDraft.map((day) => (
                  <div key={day.day} className={styles.scheduleRow}>
                    <div className={styles.scheduleLabel}>{WEEK_DAYS.find((item) => item.key === day.day)?.label || day.day}</div>

                    <label className={styles.dayOffCheck}>
                      <input
                        type="checkbox"
                        checked={day.is_day_off}
                        onChange={(event) => {
                          const isDayOff = event.target.checked;
                          updateDaySchedule(day.day, {
                            is_day_off: isDayOff,
                            start_time: isDayOff ? "" : day.start_time || "09:00",
                            end_time: isDayOff ? "" : day.end_time || "18:00",
                            break_start: isDayOff ? "" : day.break_start || "13:00",
                            break_end: isDayOff ? "" : day.break_end || "14:00",
                          });
                        }}
                      />
                      Выходной
                    </label>

                    <div className={styles.timeRange}>
                      <input
                        type="time"
                        value={day.start_time}
                        disabled={day.is_day_off}
                        onChange={(event) => updateDaySchedule(day.day, { start_time: event.target.value })}
                      />
                      <span>-</span>
                      <input
                        type="time"
                        value={day.end_time}
                        disabled={day.is_day_off}
                        onChange={(event) => updateDaySchedule(day.day, { end_time: event.target.value })}
                      />
                    </div>

                    <div className={styles.breakRow}>
                      <span>Перерыв</span>
                      <input
                        type="time"
                        value={day.break_start}
                        disabled={day.is_day_off}
                        onChange={(event) => updateDaySchedule(day.day, { break_start: event.target.value })}
                      />
                      <span>-</span>
                      <input
                        type="time"
                        value={day.break_end}
                        disabled={day.is_day_off}
                        onChange={(event) => updateDaySchedule(day.day, { break_end: event.target.value })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <footer className={styles.modalFooter}>
              <button type="button" className={styles.cancelButton} onClick={closeScheduleModal}>
                Отменить
              </button>
              <button type="button" className={styles.saveButton} onClick={() => void submitSchedule()}>
                Сохранить график
              </button>
            </footer>
          </div>
        </div>
      ) : null}

      {isBulkScheduleOpen ? (
        <div className={styles.overlay}>
          <div className={`${styles.modal} ${styles.bulkModal}`}>
            <header className={styles.modalHeader}>
              <div className={styles.modalTitleWrap}>
                <img src="/setting.svg" alt="" className={styles.modalIcon} aria-hidden />
                <h2>Составить график работы</h2>
              </div>
              <button type="button" className={styles.close} onClick={closeBulkScheduleModal}>
                ×
              </button>
            </header>

            <div className={`${styles.modalBody} ${styles.bulkBody}`}>
              <div className={styles.specialistPickerBlock}>
                <div className={styles.specialistPickerHeader}>
                  <strong>Выберите специалистов</strong>
                  <label className={styles.bulkCheckAll}>
                    <input
                      type="checkbox"
                      checked={bulkSelectedSpecialistIds.length > 0 && bulkSelectedSpecialistIds.length === activeSpecialists.length}
                      onChange={(event) => toggleBulkSelectAll(event.target.checked)}
                    />
                    Выбрать всех
                  </label>
                </div>

                <p className={styles.bulkSelectedCounter}>
                  Выбрано: <strong>{bulkSelectedSpecialistIds.length}</strong> из {activeSpecialists.length}
                </p>

                <div className={styles.specialistPickerGrid}>
                  {activeSpecialists.map((specialist) => (
                    <label key={specialist.id} className={styles.specialistCheckItem}>
                      <input
                        type="checkbox"
                        checked={bulkSelectedSpecialistIds.includes(specialist.id)}
                        onChange={() => toggleBulkSpecialistSelection(specialist.id)}
                      />
                      <span>{specialist.full_name}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className={styles.bulkSchedulePanel}>
                <div className={styles.scheduleTools}>
                  <button
                    type="button"
                    className={activeBulkSchedulePreset === "standard" ? styles.scheduleToolActive : undefined}
                    onClick={() => applyBulkTemplate("standard")}
                  >
                    Шаблон 09:00-18:00
                  </button>
                  <button
                    type="button"
                    className={activeBulkSchedulePreset === "weekend-off" ? styles.scheduleToolActive : undefined}
                    onClick={() => applyBulkTemplate("weekend-off")}
                  >
                    Выходные: Сб/Вс
                  </button>
                  <button
                    type="button"
                    className={activeBulkSchedulePreset === "copy-weekdays" ? styles.scheduleToolActive : undefined}
                    onClick={() => copyBulkDayToWeekdays("mon")}
                  >
                    Копировать Пн на Пн-Пт
                  </button>
                </div>

                {scheduleError ? <p className={styles.scheduleError}>{scheduleError}</p> : null}

                <div className={styles.scheduleGrid}>
                  {bulkScheduleDraft.map((day) => (
                    <div key={day.day} className={styles.scheduleRow}>
                      <div className={styles.scheduleLabel}>{WEEK_DAYS.find((item) => item.key === day.day)?.label || day.day}</div>

                      <label className={styles.dayOffCheck}>
                        <input
                          type="checkbox"
                          checked={day.is_day_off}
                          onChange={(event) => {
                            const isDayOff = event.target.checked;
                            updateBulkDaySchedule(day.day, {
                              is_day_off: isDayOff,
                              start_time: isDayOff ? "" : day.start_time || "09:00",
                              end_time: isDayOff ? "" : day.end_time || "18:00",
                              break_start: isDayOff ? "" : day.break_start || "13:00",
                              break_end: isDayOff ? "" : day.break_end || "14:00",
                            });
                          }}
                        />
                        Выходной
                      </label>

                      <div className={styles.timeRange}>
                        <input
                          type="time"
                          value={day.start_time}
                          disabled={day.is_day_off}
                          onChange={(event) => updateBulkDaySchedule(day.day, { start_time: event.target.value })}
                        />
                        <span>-</span>
                        <input
                          type="time"
                          value={day.end_time}
                          disabled={day.is_day_off}
                          onChange={(event) => updateBulkDaySchedule(day.day, { end_time: event.target.value })}
                        />
                      </div>

                      <div className={styles.breakRow}>
                        <span>Перерыв</span>
                        <input
                          type="time"
                          value={day.break_start}
                          disabled={day.is_day_off}
                          onChange={(event) => updateBulkDaySchedule(day.day, { break_start: event.target.value })}
                        />
                        <span>-</span>
                        <input
                          type="time"
                          value={day.break_end}
                          disabled={day.is_day_off}
                          onChange={(event) => updateBulkDaySchedule(day.day, { break_end: event.target.value })}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <footer className={styles.modalFooter}>
              <button type="button" className={styles.cancelButton} onClick={closeBulkScheduleModal}>
                Отменить
              </button>
              <button type="button" className={styles.saveButton} onClick={() => void submitBulkSchedule()}>
                Применить график
              </button>
            </footer>
          </div>
        </div>
      ) : null}
    </>
  );
}
