"use client";

import Link from "next/link";
import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { compressImageFileToDataUrl } from "../../../../lib/imageCompression";
import { formatRuPhone } from "../../../../lib/phone";
import styles from "./page.module.css";

type PartnerProfile = {
  full_name: string;
  email: string;
  phone: string;
  company_name: string;
  business_category: string;
  address: string;
  description: string;
  city: string;
  working_hours: string;
  website: string;
  instagram: string;
  business_photo_url: string;
};

type Service = { id: number; name: string; description: string; price: string | null; image_url: string; is_active: boolean };
type BusinessTable = { id: number; name: string; description: string; photo_url: string; is_active: boolean };

type TableDraft = { name: string; description: string; photo_base64: string };

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
const EMPTY_PROFILE: PartnerProfile = {
  full_name: "", email: "", phone: "", company_name: "", business_category: "", address: "",
  description: "", city: "", working_hours: "", website: "", instagram: "", business_photo_url: "",
};
const EMPTY_TABLE: TableDraft = { name: "", description: "", photo_base64: "" };

function formatPrice(value: string | null) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? `${new Intl.NumberFormat("ru-RU").format(number)} ₸` : "Цена не указана";
}

export default function PartnerBusinessPage() {
  const [partnerEmail, setPartnerEmail] = useState("");
  const [profile, setProfile] = useState<PartnerProfile>(EMPTY_PROFILE);
  const [services, setServices] = useState<Service[]>([]);
  const [tables, setTables] = useState<BusinessTable[]>([]);
  const [tableDraft, setTableDraft] = useState<TableDraft>(EMPTY_TABLE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savingTable, setSavingTable] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const profilePhotoInput = useRef<HTMLInputElement>(null);
  const tablePhotoInput = useRef<HTMLInputElement>(null);

  const isSaveDisabled = useMemo(() => saving || !profile.company_name.trim() || !profile.email.trim() || !profile.phone.trim(), [profile, saving]);
  const activeServices = useMemo(() => services.filter((service) => service.is_active), [services]);

  useEffect(() => {
    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) return;
    try {
      const user = JSON.parse(raw) as { email?: string; username?: string };
      setPartnerEmail((user.email || user.username || "").trim().toLowerCase());
    } catch {
      setLoading(false);
    }
  }, []);

  async function api(path: string, init?: RequestInit) {
    return fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Tenant": TENANT_DEFAULT, "X-Partner-Email": partnerEmail, ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  }

  async function loadBusiness() {
    if (!partnerEmail) return;
    setLoading(true);
    setError("");
    try {
      const [profileResponse, servicesResponse, tablesResponse] = await Promise.all([
        api("/partner/profile/"), api("/partner/services/?include_image=0"), api("/partner/business-tables/"),
      ]);
      const profilePayload = (await profileResponse.json()) as Partial<PartnerProfile> & { message?: string };
      const servicesPayload = (await servicesResponse.json()) as Service[];
      const tablesPayload = (await tablesResponse.json()) as BusinessTable[];
      if (!profileResponse.ok) throw new Error(profilePayload.message || "Не удалось загрузить профиль");
      setProfile({ ...EMPTY_PROFILE, ...profilePayload });
      setServices(Array.isArray(servicesPayload) ? servicesPayload : []);
      setTables(Array.isArray(tablesPayload) ? tablesPayload : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить данные бизнеса");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadBusiness(); }, [partnerEmail]);

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>, target: "business" | "table") {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const image = await compressImageFileToDataUrl(file, { maxWidth: 1280, maxHeight: 1280 });
      if (target === "business") setProfile((previous) => ({ ...previous, business_photo_url: image }));
      else setTableDraft((previous) => ({ ...previous, photo_base64: image }));
    } catch {
      setError("Не удалось обработать изображение");
    } finally {
      event.target.value = "";
    }
  }

  async function saveProfile() {
    if (!partnerEmail || isSaveDisabled) return;
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const { business_photo_url, ...profileFields } = profile;
      const body = {
        ...profileFields,
        business_photo_base64: business_photo_url.startsWith("data:image/") ? business_photo_url : undefined,
      };
      const response = await api("/partner/profile/", { method: "PATCH", body: JSON.stringify(body) });
      const payload = (await response.json()) as Partial<PartnerProfile> & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось сохранить профиль");
      const nextProfile = { ...EMPTY_PROFILE, ...payload };
      setProfile(nextProfile);
      const raw = localStorage.getItem("partner_auth_user");
      if (raw) {
        const current = JSON.parse(raw) as Record<string, string>;
        localStorage.setItem("partner_auth_user", JSON.stringify({ ...current, email: nextProfile.email, username: nextProfile.email, company_name: nextProfile.company_name }));
      }
      setMessage("Данные бизнеса сохранены");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Не удалось сохранить профиль");
    } finally {
      setSaving(false);
    }
  }

  async function saveTable() {
    if (!tableDraft.name.trim() || savingTable) return;
    setSavingTable(true);
    setError("");
    try {
      const response = await api("/partner/business-tables/", { method: "POST", body: JSON.stringify(tableDraft) });
      const payload = (await response.json()) as BusinessTable & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось сохранить стол");
      setTables((previous) => [payload, ...previous]);
      setTableDraft(EMPTY_TABLE);
      setMessage("Стол добавлен");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Не удалось сохранить стол");
    } finally {
      setSavingTable(false);
    }
  }

  async function toggleTable(table: BusinessTable) {
    try {
      const response = await api(`/partner/business-tables/${table.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !table.is_active }) });
      const payload = (await response.json()) as BusinessTable & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось изменить стол");
      setTables((previous) => previous.map((item) => item.id === payload.id ? payload : item));
    } catch (toggleError) {
      setError(toggleError instanceof Error ? toggleError.message : "Не удалось изменить стол");
    }
  }

  function updateProfile<K extends keyof PartnerProfile>(key: K, value: PartnerProfile[K]) {
    setProfile((previous) => ({ ...previous, [key]: value }));
  }

  return (
    <section className={styles.page}>
      <div className={styles.headerRow}>
        <div><h2 className={styles.pageTitle}>Мой бизнес</h2><p className={styles.pageSubtitle}>Управление информацией о вашем бизнесе</p></div>
        <button type="button" className={styles.saveTopButton} disabled={isSaveDisabled} onClick={() => void saveProfile()}>{saving ? "Сохраняем..." : "Сохранить"}</button>
      </div>
      {error && <p className={styles.errorMessage}>{error}</p>}
      {message && <p className={styles.successMessage}>{message}</p>}

      <div className={styles.grid}>
        <div className={styles.leftColumn}>
          <section className={styles.sectionCard}>
            <h3>Основная информация</h3>
            <div className={styles.fieldGrid}>
              <label><span>Название бизнеса</span><input value={profile.company_name} onChange={(event) => updateProfile("company_name", event.target.value)} disabled={loading} /></label>
              <label><span>Основная категория</span><input value={profile.business_category} onChange={(event) => updateProfile("business_category", event.target.value)} disabled={loading} /></label>
              <label><span>Описание</span><textarea value={profile.description} onChange={(event) => updateProfile("description", event.target.value)} disabled={loading} /></label>
              <label><span>Город</span><input value={profile.city} onChange={(event) => updateProfile("city", event.target.value)} disabled={loading} /></label>
              <label><span>Адрес</span><input value={profile.address} onChange={(event) => updateProfile("address", event.target.value)} disabled={loading} /></label>
              <label><span>График работы</span><input placeholder="Пн-Пт: 09:00-20:00" value={profile.working_hours} onChange={(event) => updateProfile("working_hours", event.target.value)} disabled={loading} /></label>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <h3>Контакты</h3>
            <div className={styles.fieldGrid}>
              <label><span>Контактное лицо</span><input value={profile.full_name} onChange={(event) => updateProfile("full_name", event.target.value)} disabled={loading} /></label>
              <label><span>Телефон</span><input value={profile.phone} onChange={(event) => updateProfile("phone", formatRuPhone(event.target.value))} inputMode="tel" disabled={loading} /></label>
              <label><span>Email</span><input value={profile.email} onChange={(event) => updateProfile("email", event.target.value)} disabled={loading} /></label>
              <label><span>Web-сайт</span><input placeholder="https://example.kz" value={profile.website} onChange={(event) => updateProfile("website", event.target.value)} disabled={loading} /></label>
              <label><span>Instagram</span><input placeholder="@mybusiness" value={profile.instagram} onChange={(event) => updateProfile("instagram", event.target.value)} disabled={loading} /></label>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}><h3>Предложения</h3><Link className={styles.ghostButton} href="/partner/dashboard/manage">Управлять услугами</Link></div>
            {activeServices.length ? <div className={styles.itemList}>{activeServices.map((service) => <article key={service.id} className={styles.listItem}>{service.image_url ? <img src={service.image_url} alt="" /> : <div className={styles.itemPlaceholder} /> }<div><strong>{service.name}</strong><p>{service.description || formatPrice(service.price)}</p></div><span>{formatPrice(service.price)}</span></article>)}</div> : <p className={styles.emptyText}>Добавьте услуги в разделе «Услуги и категории».</p>}
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}><h3>Столы</h3><span className={styles.counter}>{tables.filter((table) => table.is_active).length}</span></div>
            <div className={styles.tableForm}>
              <button type="button" className={styles.uploadBox} onClick={() => tablePhotoInput.current?.click()}>{tableDraft.photo_base64 ? <img src={tableDraft.photo_base64} alt="Фото стола" /> : "Добавить фото"}</button>
              <input ref={tablePhotoInput} className={styles.fileInput} type="file" accept="image/*" onChange={(event) => void handlePhotoChange(event, "table")} />
              <label><span>Название стола</span><input value={tableDraft.name} onChange={(event) => setTableDraft((previous) => ({ ...previous, name: event.target.value }))} /></label>
              <label><span>Описание</span><textarea value={tableDraft.description} onChange={(event) => setTableDraft((previous) => ({ ...previous, description: event.target.value }))} /></label>
              <button type="button" className={styles.saveButton} disabled={!tableDraft.name.trim() || savingTable} onClick={() => void saveTable()}>{savingTable ? "Сохраняем..." : "Сохранить стол"}</button>
            </div>
            {tables.length ? <div className={styles.itemList}>{tables.map((table) => <article key={table.id} className={styles.listItem}>{table.photo_url ? <img src={table.photo_url} alt="" /> : <div className={styles.itemPlaceholder} />}<div><strong>{table.name}</strong><p>{table.description || "Описание не указано"}</p></div><button type="button" className={styles.archiveButton} onClick={() => void toggleTable(table)}>{table.is_active ? "Архивировать" : "Вернуть"}</button></article>)}</div> : null}
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}><h3>Фотография бизнеса</h3><button type="button" className={styles.ghostButton} onClick={() => profilePhotoInput.current?.click()}>Загрузить фото</button></div>
            <button type="button" className={styles.photoBox} onClick={() => profilePhotoInput.current?.click()}>{profile.business_photo_url ? <img src={profile.business_photo_url} alt="Фотография бизнеса" /> : "Добавить фото"}</button>
            <input ref={profilePhotoInput} className={styles.fileInput} type="file" accept="image/*" onChange={(event) => void handlePhotoChange(event, "business")} />
          </section>
        </div>

        <aside className={styles.previewCard}>
          <span className={styles.previewLabel}>Предпросмотр</span>
          <div className={styles.phoneMock}><div className={styles.phoneScreen}>
            <h4>Ваша карточка</h4>
            {profile.business_photo_url ? <img className={styles.mockImage} src={profile.business_photo_url} alt="" /> : <div className={styles.mockImage}>Добавить фото</div>}
            <p className={styles.mockBusinessName}>{profile.company_name || "Ваш бизнес"}</p>
            <p className={styles.mockCategory}>{profile.business_category || "Категория бизнеса"}</p>
            <p className={styles.mockDescription}>{profile.description || "Добавьте описание вашего бизнеса"}</p>
            <div className={styles.mockPills}><span className={styles.mockPillActive}>Услуги</span><span className={styles.mockPill}>Отзывы</span></div>
            <div className={styles.mockOfferCard}><strong>{profile.city || "Город"}</strong><p>{profile.address || "Добавьте адрес вашего бизнеса"}</p><p>{profile.working_hours || "График работы не указан"}</p></div>
          </div></div>
        </aside>
      </div>
    </section>
  );
}
