"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";
import { compressImageFileToDataUrl } from "../../../../lib/imageCompression";

type Category = { id: number; name: string; is_active: boolean };
type ServiceKind = {
  id: number;
  name: string;
  category: number;
  category_name: string;
  is_active: boolean;
};
type Service = {
  id: number;
  name: string;
  category: number;
  category_name: string;
  kind: number | null;
  kind_name: string | null;
  details?: Record<string, number>;
  description: string;
  duration_minutes: number;
  price: string | null;
  discount_percent: number;
  is_subscription: boolean;
  image_url: string;
  image_base64?: string;
  is_promo: boolean;
  is_active: boolean;
};
type Manager = { id: number; full_name: string; phone: string; is_active: boolean };
type Booking = {
  id: number;
  service_name: string;
  manager_name: string | null;
  starts_at: string;
  client_name: string;
  client_phone: string;
  status: string;
};

type OfferFormState = {
  name: string;
  categoryId: string;
  kindId: string;
  description: string;
  imageUrl: string;
  price: string;
  durationMinutes: string;
  discountPercent: string;
  isSubscription: boolean;
  maxPeople: string;
  minPeople: string;
  tableCapacity: string;
  holdMinutes: string;
};

type DialogMode = "add" | "edit" | "archive" | "unarchive";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

export default function PartnerManagePage() {
  const tenant = TENANT_DEFAULT;
  const [authResolved, setAuthResolved] = useState(false);
  const [categories, setCategories] = useState<Category[]>([]);
  const [kinds, setKinds] = useState<ServiceKind[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [, setManagers] = useState<Manager[]>([]);
  const [, setBookings] = useState<Booking[]>([]);

  const [offerQuery, setOfferQuery] = useState("");
  const [offerTab, setOfferTab] = useState<"active" | "archived" | "all">("active");
  const [offerPageSize, setOfferPageSize] = useState<10 | 20 | 50>(10);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [dialogMode, setDialogMode] = useState<DialogMode>("add");
  const [editingOffer, setEditingOffer] = useState<Service | null>(null);
  const [isSavingOffer, setIsSavingOffer] = useState(false);
  const [offerSaveError, setOfferSaveError] = useState("");
  const [partnerEmail, setPartnerEmail] = useState("");
  const [offerForm, setOfferForm] = useState<OfferFormState>({
    name: "",
    categoryId: "",
    kindId: "",
    description: "",
    imageUrl: "",
    price: "",
    durationMinutes: "60",
    discountPercent: "",
    isSubscription: true,
    maxPeople: "",
    minPeople: "",
    tableCapacity: "",
    holdMinutes: "",
  });

  const canCreateService = useMemo(() => categories.length > 0, [categories.length]);

  const kindsForSelectedCategory = useMemo(() => {
    if (!offerForm.categoryId) {
      return [];
    }
    const selectedCategoryId = Number(offerForm.categoryId);
    return kinds.filter((item) => item.is_active && item.category === selectedCategoryId);
  }, [kinds, offerForm.categoryId]);

  const selectedCategoryName = useMemo(() => {
    if (!offerForm.categoryId) {
      return "";
    }
    return categories.find((item) => String(item.id) === offerForm.categoryId)?.name ?? "";
  }, [categories, offerForm.categoryId]);

  const visibleServices = useMemo(() => {
    const text = offerQuery.toLowerCase();
    return services
      .filter((item) => item.name.toLowerCase().includes(text))
      .filter((item) => {
        if (offerTab === "all") {
          return true;
        }
        return offerTab === "active" ? item.is_active : !item.is_active;
      })
      .sort((left, right) => right.id - left.id);
  }, [offerQuery, offerTab, services]);

  const displayedServices = useMemo(() => {
    return visibleServices.slice(0, offerPageSize);
  }, [visibleServices, offerPageSize]);

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
    try {
      const [catsRes, kindsRes] = await Promise.all([api("/partner/categories/"), api("/partner/service-kinds/")]);

      const cats = (await catsRes.json()) as Category[];
      const allKinds = (await kindsRes.json()) as ServiceKind[];

      setCategories(Array.isArray(cats) ? cats : []);
      setKinds(Array.isArray(allKinds) ? allKinds : []);
      if (!partnerEmail) {
        setServices([]);
        setManagers([]);
        setBookings([]);
        return;
      }

      const [srvRes, mgrRes, bookRes] = await Promise.all([
        api("/partner/services/?include_image=0"),
        api("/partner/managers/"),
        api("/partner/bookings/"),
      ]);

      const srv = (await srvRes.json()) as Service[];
      const mgr = (await mgrRes.json()) as Manager[];
      const book = (await bookRes.json()) as Booking[];

      setServices(Array.isArray(srv) ? srv : []);
      setManagers(Array.isArray(mgr) ? mgr : []);
      setBookings(Array.isArray(book) ? book : []);

      if (!offerForm.categoryId && Array.isArray(cats) && cats.length > 0) {
        const defaultCategoryId = String(cats[0].id);
        const defaultKind = (Array.isArray(allKinds) ? allKinds : []).find(
          (item) => item.is_active && String(item.category) === defaultCategoryId,
        );
        setOfferForm((prev) => ({
          ...prev,
          categoryId: defaultCategoryId,
          kindId: defaultKind ? String(defaultKind.id) : "",
        }));
      }

    } catch {
      // Keep UI clean: load errors are intentionally silent on this screen.
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
      // ignore invalid local storage value
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

  function openCreateModal() {
    const defaultCategoryId = categories[0] ? String(categories[0].id) : "";
    const defaultKind = kinds.find((item) => item.is_active && String(item.category) === defaultCategoryId);
    setDialogMode("add");
    setEditingOffer(null);
    setOfferForm({
      name: "",
      categoryId: defaultCategoryId,
      kindId: defaultKind ? String(defaultKind.id) : "",
      description: "",
      imageUrl: "",
      price: "",
      durationMinutes: "60",
      discountPercent: "20",
      isSubscription: true,
      maxPeople: "",
      minPeople: "",
      tableCapacity: "",
      holdMinutes: "",
    });
    setOfferSaveError("");
    setIsSavingOffer(false);
    setIsModalOpen(true);
  }

  function openEditModal(service: Service) {
    setDialogMode("edit");
    setEditingOffer(service);
    setOfferForm({
      name: service.name,
      categoryId: String(service.category),
      kindId: service.kind ? String(service.kind) : "",
      description: service.description || "",
      imageUrl: service.image_url || service.image_base64 || "",
      price: service.price ?? "0",
      durationMinutes: String(service.duration_minutes || 60),
      discountPercent: String(service.discount_percent || 0),
      isSubscription: service.is_subscription,
      maxPeople: service.details?.max_people ? String(service.details.max_people) : "",
      minPeople: service.details?.min_people ? String(service.details.min_people) : "",
      tableCapacity: service.details?.table_capacity ? String(service.details.table_capacity) : "",
      holdMinutes: service.details?.hold_minutes ? String(service.details.hold_minutes) : "",
    });
    setOfferSaveError("");
    setIsSavingOffer(false);
    setIsModalOpen(true);
  }

  function openArchiveModal(service: Service) {
    setDialogMode(service.is_active ? "archive" : "unarchive");
    setEditingOffer(service);
    setIsModalOpen(true);
  }

  async function onServiceImageSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }
    try {
      const value = await compressImageFileToDataUrl(file);
      setOfferForm((prev) => ({ ...prev, imageUrl: value }));
    } catch {
      setOfferSaveError("Не удалось обработать изображение. Попробуйте другой файл.");
    }
  }

  async function submitOffer(event: FormEvent) {
    event.preventDefault();
    if (isSavingOffer) {
      return;
    }
    setOfferSaveError("");

    if (!offerForm.name.trim() || !offerForm.categoryId || !offerForm.kindId) {
      setOfferSaveError("Заполните название, категорию и направление услуги");
      return;
    }

    const detailsPayload: Record<string, number> = {};
    if (selectedCategoryName === "Спорт") {
      if (offerForm.maxPeople.trim()) {
        detailsPayload.max_people = Number(offerForm.maxPeople);
      }
      if (offerForm.minPeople.trim()) {
        detailsPayload.min_people = Number(offerForm.minPeople);
      }
    }
    if (selectedCategoryName === "Кафе и рестораны") {
      if (offerForm.tableCapacity.trim()) {
        detailsPayload.table_capacity = Number(offerForm.tableCapacity);
      }
      if (offerForm.holdMinutes.trim()) {
        detailsPayload.hold_minutes = Number(offerForm.holdMinutes);
      }
    }

    setIsSavingOffer(true);

    const response = await api(editingOffer && dialogMode === "edit" ? `/partner/services/${editingOffer.id}/` : "/partner/services/", {
      method: editingOffer && dialogMode === "edit" ? "PATCH" : "POST",
      body: JSON.stringify({
        name: offerForm.name,
        category: Number(offerForm.categoryId),
        kind: Number(offerForm.kindId),
        details: detailsPayload,
        description: offerForm.description,
        image_base64: offerForm.imageUrl,
        duration_minutes: Number(offerForm.durationMinutes || 60),
        price: Number(offerForm.price || 0),
        discount_percent: Number(offerForm.discountPercent || 0),
        is_subscription: offerForm.isSubscription,
        is_promo: Number(offerForm.discountPercent || 0) > 0,
        is_active: true,
      }),
    });

    if (!response.ok) {
      setOfferSaveError(editingOffer ? "Не удалось сохранить изменения" : "Не удалось создать услугу");
      setIsSavingOffer(false);
      return;
    }

    setIsModalOpen(false);
    setIsSavingOffer(false);
    await loadData();
  }

  async function submitArchiveDecision() {
    if (!editingOffer) {
      return;
    }

    const shouldActivate = dialogMode === "unarchive";
    const response = await api(`/partner/services/${editingOffer.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: shouldActivate }),
    });
    if (!response.ok) {
      return;
    }

    setIsModalOpen(false);
    await loadData();
  }

  return (
    <>
      <main className={styles.page}>
        <section className={styles.block}>
          <div className={styles.blockHeadRow}>
            <div className={styles.blockHeaderLeft}>
              <h2>Предложения</h2>
            </div>

          </div>

          <div className={styles.controlsPanel}>
            <div className={styles.blockTopRow}>
              <div className={styles.searchWrap}>
                <img src="/search.svg" alt="" className={styles.searchIconImage} aria-hidden />
                <input
                  className={styles.search}
                  placeholder="Поиск категорий услуг"
                  value={offerQuery}
                  onChange={(event) => setOfferQuery(event.target.value)}
                />
              </div>
              <button
                type="button"
                className={styles.addButton}
                onClick={openCreateModal}
                disabled={!canCreateService}
              >
                <span className={styles.plusIcon} aria-hidden>+</span>
                Добавить
              </button>
            </div>

            <div className={styles.filterRow}>
              <button
                type="button"
                onClick={() => setOfferTab("active")}
                className={offerTab === "active" ? styles.pillActive : styles.pill}
              >
                Активные({services.filter((item) => item.is_active).length})
              </button>
              <button
                type="button"
                onClick={() => setOfferTab("archived")}
                className={offerTab === "archived" ? styles.pillActive : styles.pill}
              >
                Архивные({services.filter((item) => !item.is_active).length})
              </button>
              <button
                type="button"
                onClick={() => setOfferTab("all")}
                className={offerTab === "all" ? styles.pillActive : styles.pill}
              >
                Все
              </button>
            </div>
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Фото</th>
                  <th>Название предложении</th>
                  <th>Категория</th>
                  <th>Вид услуги</th>
                  <th>Стоимость</th>
                  <th>Длительность</th>
                  <th>Скидка</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {displayedServices.map((service) => (
                  <tr key={service.id}>
                    <td>
                      {service.image_url || service.image_base64 ? (
                        <img
                          src={service.image_url || service.image_base64}
                          alt="Фото услуги"
                          className={styles.servicePhoto}
                          loading="lazy"
                          decoding="async"
                        />
                      ) : (
                        <span className={styles.avatarDot} />
                      )}
                    </td>
                    <td>{service.name}</td>
                    <td>{service.category_name}</td>
                    <td>{service.kind_name || "-"}</td>
                    <td>{service.price ? `${service.price} ₸` : "-"}</td>
                    <td>{service.duration_minutes} мин</td>
                    <td>{service.discount_percent > 0 ? `${service.discount_percent}%` : "-"}</td>
                    <td>
                      <span className={styles.rowActions}>
                        <button type="button" className={styles.iconButton} onClick={() => openEditModal(service)}>
                          <img src="/change.svg" alt="" className={styles.actionIcon} aria-hidden />
                        </button>
                        <button type="button" className={styles.iconButton} onClick={() => openArchiveModal(service)}>
                          <img src="/Archieve.svg" alt="" className={styles.actionIcon} aria-hidden />
                        </button>
                      </span>
                    </td>
                  </tr>
                ))}
                {!displayedServices.length ? (
                  <tr>
                    <td colSpan={8} className={styles.empty}>
                      Нет предложений
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>

          <div className={styles.footerTools}>
            <label htmlFor="offers-limit">Показывать</label>
            <select
              id="offers-limit"
              value={offerPageSize}
              onChange={(event) => setOfferPageSize(Number(event.target.value) as 10 | 20 | 50)}
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
            </select>
            <span>
              Показано {displayedServices.length} из {visibleServices.length}
            </span>
          </div>
        </section>

      </main>

      {isModalOpen ? (
        <div className={styles.overlay}>
          {dialogMode === "archive" || dialogMode === "unarchive" ? (
            <div className={styles.statusModal}>
              <div className={styles.statusBody}>
                <div className={styles.statusIconWrap}>
                  <img src="/Archieve.svg" alt="" className={styles.statusIconImage} aria-hidden />
                </div>
                <div className={styles.statusTextBlock}>
                  <h3>{dialogMode === "archive" ? "Архивировать предложение" : "Разархивировать предложение"}</h3>
                  <p>
                    Вы уверены, что хотите {dialogMode === "archive" ? "архивировать" : "разархивировать"} “
                    <strong>{editingOffer?.name ?? "Предложение"}</strong>” ?
                  </p>
                </div>
              </div>

              <div className={styles.statusActions}>
                <button type="button" className={styles.statusCancelButton} onClick={() => setIsModalOpen(false)}>
                  Отменить
                </button>
                <button type="button" className={styles.statusWarningButton} onClick={() => void submitArchiveDecision()}>
                  {dialogMode === "archive" ? "Архивировать" : "Разархивировать"}
                </button>
              </div>
            </div>
          ) : (
            <form className={styles.modal} onSubmit={submitOffer}>
              <header className={styles.modalHeader}>
                <div className={styles.modalTitleWrap}>
                  <img src="/modal_icon.svg" alt="" className={styles.modalIcon} aria-hidden />
                  <h2>{dialogMode === "edit" ? "Редактировать предложение" : "Добавить предложении"}</h2>
                </div>
                <button type="button" className={styles.close} onClick={() => setIsModalOpen(false)}>
                  ×
                </button>
              </header>

              <div className={styles.modalBody}>
                <label>
                  Название предложении
                  <input
                    value={offerForm.name}
                    onChange={(event) => setOfferForm((prev) => ({ ...prev, name: event.target.value }))}
                    placeholder="Комплексная мойка"
                    required
                  />
                </label>

                <label>
                  Категория услуг
                  <select
                    value={offerForm.categoryId}
                    onChange={(event) => {
                      const selectedCategoryId = event.target.value;
                      const firstKind = kinds.find(
                        (item) => item.is_active && String(item.category) === selectedCategoryId,
                      );
                      setOfferForm((prev) => ({
                        ...prev,
                        categoryId: selectedCategoryId,
                        kindId: firstKind ? String(firstKind.id) : "",
                        maxPeople: "",
                        minPeople: "",
                        tableCapacity: "",
                        holdMinutes: "",
                      }));
                    }}
                    required
                  >
                    {categories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                </label>

                <label>
                  Направление услуги
                  <select
                    value={offerForm.kindId}
                    onChange={(event) => setOfferForm((prev) => ({ ...prev, kindId: event.target.value }))}
                    required
                  >
                    <option value="">Не выбрано</option>
                    {kindsForSelectedCategory.map((kind) => (
                      <option key={kind.id} value={kind.id}>
                        {kind.name}
                      </option>
                    ))}
                  </select>
                  {offerSaveError ? <p className={styles.formError}>{offerSaveError}</p> : null}
                </label>

                <label>
                  Описание
                  <textarea
                    value={offerForm.description}
                    onChange={(event) => setOfferForm((prev) => ({ ...prev, description: event.target.value }))}
                    rows={4}
                  />
                </label>

                <div className={styles.discountRow}>
                  <label>
                    Стоимость (₸)
                    <input
                      value={offerForm.price}
                      onChange={(event) => setOfferForm((prev) => ({ ...prev, price: event.target.value }))}
                      inputMode="numeric"
                    />
                  </label>

                  <label>
                    Длительность(мин)
                    <input
                      value={offerForm.durationMinutes}
                      onChange={(event) =>
                        setOfferForm((prev) => ({ ...prev, durationMinutes: event.target.value }))
                      }
                      inputMode="numeric"
                    />
                  </label>
                </div>

                {selectedCategoryName === "Спорт" ? (
                  <div className={styles.discountRow}>
                    <label>
                      Максимум участников
                      <input
                        value={offerForm.maxPeople}
                        onChange={(event) => setOfferForm((prev) => ({ ...prev, maxPeople: event.target.value }))}
                        inputMode="numeric"
                        placeholder="например: 10"
                      />
                    </label>

                    <label>
                      Минимум участников
                      <input
                        value={offerForm.minPeople}
                        onChange={(event) => setOfferForm((prev) => ({ ...prev, minPeople: event.target.value }))}
                        inputMode="numeric"
                        placeholder="например: 2"
                      />
                    </label>
                  </div>
                ) : null}

                {selectedCategoryName === "Кафе и рестораны" ? (
                  <div className={styles.discountRow}>
                    <label>
                      Вместимость стола
                      <input
                        value={offerForm.tableCapacity}
                        onChange={(event) => setOfferForm((prev) => ({ ...prev, tableCapacity: event.target.value }))}
                        inputMode="numeric"
                        placeholder="например: 6"
                      />
                    </label>

                    <label>
                      Удержание брони (мин)
                      <input
                        value={offerForm.holdMinutes}
                        onChange={(event) => setOfferForm((prev) => ({ ...prev, holdMinutes: event.target.value }))}
                        inputMode="numeric"
                        placeholder="например: 15"
                      />
                    </label>
                  </div>
                ) : null}

                <div className={styles.discountRow}>
                  <label className={styles.checkLabel}>
                    <input
                      type="checkbox"
                      checked={offerForm.isSubscription}
                      onChange={(event) =>
                        setOfferForm((prev) => ({ ...prev, isSubscription: event.target.checked }))
                      }
                    />
                    Доступно по подписке
                  </label>

                  <label>
                    Скидки (%)
                    <input
                      value={offerForm.discountPercent}
                      onChange={(event) =>
                        setOfferForm((prev) => ({ ...prev, discountPercent: event.target.value }))
                      }
                      inputMode="numeric"
                    />
                  </label>
                </div>

                <label className={styles.previewBox}>
                  {offerForm.imageUrl ? (
                    <img src={offerForm.imageUrl} alt="Фото услуги" className={styles.previewImage} loading="lazy" decoding="async" />
                  ) : (
                    <span className={styles.previewHint}>🖼 Добавить фото</span>
                  )}
                  <input type="file" accept="image/*" className={styles.hiddenFileInput} onChange={onServiceImageSelected} />
                  {dialogMode === "edit" && offerForm.imageUrl ? (
                    <button
                      type="button"
                      className={styles.trash}
                      onClick={() => setOfferForm((prev) => ({ ...prev, imageUrl: "" }))}
                      aria-label="Удалить фото"
                    >
                      🗑
                    </button>
                  ) : null}
                </label>
              </div>

              <footer className={styles.modalFooter}>
                <button type="button" className={styles.cancelButton} onClick={() => setIsModalOpen(false)}>
                  Отменить
                </button>
                <button type="submit" className={styles.saveButton} disabled={isSavingOffer}>
                  {isSavingOffer ? "Сохранение..." : dialogMode === "edit" ? "Сохранить" : "Создать"}
                </button>
              </footer>
            </form>
          )}
        </div>
      ) : null}
    </>
  );
}
