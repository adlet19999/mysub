"use client";

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import styles from "./page.module.css";

type ServiceKind = {
  id: number;
  name: string;
  category: number;
  category_name: string;
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
  photo_base64: string;
  working_schedule: WorkingDaySchedule[];
  service_kind_ids: number[];
  service_kind_names: string[];
  is_active: boolean;
};

type SpecialistFormState = {
  fullName: string;
  description: string;
  pendingServiceGroupKey: string;
  selectedServiceGroupKeys: string[];
  photoBase64: string;
};

type ServiceGroupOption = {
  key: string;
  label: string;
  kindIds: number[];
};

type ModalMode = "create" | "edit";
type ToastTone = "success" | "error";
type ToastState = { text: string; tone: ToastTone };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000/api/v1";
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

function splitKindName(value: string): { serviceGroup: string; subtype: string } {
  const [left, ...rightParts] = value.split(":");
  const serviceGroup = (left || "").trim();
  const subtypeRaw = rightParts.join(":").trim();
  return {
    serviceGroup,
    subtype: subtypeRaw || serviceGroup,
  };
}

export default function SpecialistsPage() {
  const tenant = TENANT_DEFAULT;
  const [partnerEmail, setPartnerEmail] = useState("");

  const [kinds, setKinds] = useState<ServiceKind[]>([]);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);

  const [searchQuery, setSearchQuery] = useState("");
  const [tab, setTab] = useState<"active" | "archived" | "all">("active");
  const [toast, setToast] = useState<ToastState | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [archiveTarget, setArchiveTarget] = useState<Specialist | null>(null);
  const [modalMode, setModalMode] = useState<ModalMode>("create");
  const [editingSpecialist, setEditingSpecialist] = useState<Specialist | null>(null);
  const [kindError, setKindError] = useState("");
  const [form, setForm] = useState<SpecialistFormState>({
    fullName: "",
    description: "",
    pendingServiceGroupKey: "",
    selectedServiceGroupKeys: [],
    photoBase64: "",
  });
  const photoInputRef = useRef<HTMLInputElement | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showToast(text: string, tone: ToastTone = "success") {
    if (toastTimerRef.current) {
      clearTimeout(toastTimerRef.current);
    }
    setToast({ text, tone });
    toastTimerRef.current = setTimeout(() => setToast(null), 2200);
  }

  const availableKinds = useMemo(() => {
    return kinds.filter((item) => item.is_active).sort((left, right) => left.name.localeCompare(right.name));
  }, [kinds]);

  const availableServiceGroups = useMemo<ServiceGroupOption[]>(() => {
    const byKey = new Map<string, ServiceGroupOption>();
    for (const kind of availableKinds) {
      const parsed = splitKindName(kind.name);
      const groupLabel = parsed.serviceGroup || kind.name;
      const key = `${kind.category}:${groupLabel.toLowerCase()}`;
      const existing = byKey.get(key);
      if (existing) {
        existing.kindIds.push(kind.id);
      } else {
        byKey.set(key, { key, label: groupLabel, kindIds: [kind.id] });
      }
    }
    return Array.from(byKey.values()).sort((left, right) => left.label.localeCompare(right.label));
  }, [availableKinds]);

  function getServiceGroupKeysFromKindIds(kindIds: number[]) {
    const keySet = new Set<string>();
    for (const kindId of kindIds) {
      const kind = availableKinds.find((item) => item.id === kindId);
      if (!kind) {
        continue;
      }
      const parsed = splitKindName(kind.name);
      const groupLabel = parsed.serviceGroup || kind.name;
      keySet.add(`${kind.category}:${groupLabel.toLowerCase()}`);
    }
    return Array.from(keySet);
  }

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
      const [kindsRes, specialistsRes] = await Promise.all([api("/partner/service-kinds/"), api("/partner/specialists/")]);

      if (!kindsRes.ok || !specialistsRes.ok) {
        return;
      }

      const kindsPayload = (await kindsRes.json()) as ServiceKind[];
      const specialistsPayload = (await specialistsRes.json()) as Specialist[];

      setKinds(Array.isArray(kindsPayload) ? kindsPayload : []);
      setSpecialists(
        Array.isArray(specialistsPayload)
          ? specialistsPayload.map((item) => ({ ...item, working_schedule: normalizeWorkingSchedule(item.working_schedule) }))
          : [],
      );
    } catch {
      // Keep this dashboard resilient to temporary API connectivity issues.
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
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [partnerEmail]);

  function openCreateModal() {
    setModalMode("create");
    setEditingSpecialist(null);
    setKindError("");
    setForm({
      fullName: "",
      description: "",
      pendingServiceGroupKey: availableServiceGroups[0]?.key ?? "",
      selectedServiceGroupKeys: [],
      photoBase64: "",
    });
    setIsModalOpen(true);
  }

  function openEditModal(specialist: Specialist) {
    setModalMode("edit");
    setEditingSpecialist(specialist);
    setKindError("");
    setForm({
      fullName: specialist.full_name,
      description: specialist.description || "",
      pendingServiceGroupKey: availableServiceGroups[0]?.key ?? "",
      selectedServiceGroupKeys: getServiceGroupKeysFromKindIds(specialist.service_kind_ids),
      photoBase64: specialist.photo_base64 || "",
    });
    setIsModalOpen(true);
  }

  function addServiceGroup() {
    const selectedKey = form.pendingServiceGroupKey;
    if (!selectedKey || form.selectedServiceGroupKeys.includes(selectedKey)) {
      return;
    }
    setKindError("");
    setForm((prev) => ({ ...prev, selectedServiceGroupKeys: [...prev.selectedServiceGroupKeys, selectedKey] }));
  }

  function removeServiceGroup(groupKey: string) {
    setForm((prev) => {
      const nextSelected = prev.selectedServiceGroupKeys.filter((item) => item !== groupKey);
      if (nextSelected.length) {
        setKindError("");
      }
      return { ...prev, selectedServiceGroupKeys: nextSelected };
    });
  }

  function onSelectPhoto(file: File | null) {
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      setForm((prev) => ({ ...prev, photoBase64: result }));
    };
    reader.readAsDataURL(file);
  }

  function clearPhoto() {
    setForm((prev) => ({ ...prev, photoBase64: "" }));
    if (photoInputRef.current) {
      photoInputRef.current.value = "";
    }
  }

  async function submitSpecialist(event: FormEvent) {
    event.preventDefault();

    if (!form.fullName.trim()) {
      return;
    }

    if (!form.selectedServiceGroupKeys.length) {
      setKindError("Выберите хотя бы одну услугу (2 уровень)");
      return;
    }

    const mappedKindIds = availableServiceGroups
      .filter((group) => form.selectedServiceGroupKeys.includes(group.key))
      .flatMap((group) => group.kindIds);

    if (!mappedKindIds.length) {
      setKindError("Для выбранной услуги не найдены подвиды");
      return;
    }

    setKindError("");

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
          photo_base64: form.photoBase64,
          working_schedule: defaultWorkingSchedule(),
          service_kind_ids: mappedKindIds,
          is_active: true,
        }),
      },
    );
    if (!response.ok) {
      return;
    }

    setIsModalOpen(false);
    await loadData();
    showToast(modalMode === "create" ? "Специалист успешно добавлен" : "Специалист успешно обновлен", "success");
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

            <button type="button" className={styles.addButton} onClick={openCreateModal} disabled={!partnerEmail}>
              <span className={styles.plusIcon} aria-hidden>+</span>
              Добавить специалиста
            </button>
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

          {!partnerEmail ? (
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

                {specialist.photo_base64 ? (
                  <img src={specialist.photo_base64} alt="" className={styles.cardPhoto} />
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
                    value={form.pendingServiceGroupKey}
                    onChange={(event) => setForm((prev) => ({ ...prev, pendingServiceGroupKey: event.target.value }))}
                    required={!form.selectedServiceGroupKeys.length}
                  >
                    <option value="" disabled>Выберите услугу (2 уровень)</option>
                    {availableServiceGroups.map((group) => (
                      <option key={group.key} value={group.key}>
                        {group.label}
                      </option>
                    ))}
                  </select>
                  <button type="button" className={styles.addKindButton} onClick={addServiceGroup}>
                    Добавить
                  </button>
                </div>
                <div className={styles.kindChips}>
                  {form.selectedServiceGroupKeys.map((groupKey) => {
                    const group = availableServiceGroups.find((item) => item.key === groupKey);
                    if (!group) {
                      return null;
                    }
                    return (
                      <button
                        key={group.key}
                        type="button"
                        className={styles.kindChip}
                        onClick={() => removeServiceGroup(group.key)}
                        title="Удалить"
                      >
                        {group.label}
                        <span aria-hidden>×</span>
                      </button>
                    );
                  })}
                </div>
                {kindError ? <p className={styles.kindError}>{kindError}</p> : null}
              </label>

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
    </>
  );
}
