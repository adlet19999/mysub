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

type Service = {
  id: number;
  name: string;
  description: string;
  price: string | null;
  image_url: string;
  discount_percent: number;
  is_subscription: boolean;
  is_active: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
const EMPTY_PROFILE: PartnerProfile = {
  full_name: "", email: "", phone: "", company_name: "", business_category: "", address: "",
  description: "", city: "", working_hours: "", website: "", instagram: "", business_photo_url: "",
};

function formatPrice(value: string | null) {
  const number = Number(value || 0);
  return Number.isFinite(number) && number > 0 ? `${new Intl.NumberFormat("ru-RU").format(number)} ₸` : "Цена не указана";
}

function discountedPrice(service: Service) {
  const price = Number(service.price || 0);
  if (!Number.isFinite(price) || price <= 0) return "Цена не указана";
  return formatPrice(String(price * (1 - Math.min(100, service.discount_percent || 0) / 100)));
}

export default function PartnerBusinessPage() {
  const [partnerEmail, setPartnerEmail] = useState("");
  const [profile, setProfile] = useState<PartnerProfile>(EMPTY_PROFILE);
  const [services, setServices] = useState<Service[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [previewTab, setPreviewTab] = useState<"services" | "about">("services");
  const [addedServiceIds, setAddedServiceIds] = useState<number[]>([]);
  const profilePhotoInput = useRef<HTMLInputElement>(null);

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
      const [profileResponse, servicesResponse] = await Promise.all([
        api("/partner/profile/"), api("/partner/services/?include_image=0"),
      ]);
      const profilePayload = (await profileResponse.json()) as Partial<PartnerProfile> & { message?: string };
      const servicesPayload = (await servicesResponse.json()) as Service[];
      if (!profileResponse.ok) throw new Error(profilePayload.message || "Не удалось загрузить профиль");
      setProfile({ ...EMPTY_PROFILE, ...profilePayload });
      setServices(Array.isArray(servicesPayload) ? servicesPayload : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить данные бизнеса");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadBusiness(); }, [partnerEmail]);

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    try {
      const image = await compressImageFileToDataUrl(file, { maxWidth: 1280, maxHeight: 1280 });
      setProfile((previous) => ({ ...previous, business_photo_url: image }));
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

  function updateProfile<K extends keyof PartnerProfile>(key: K, value: PartnerProfile[K]) {
    setProfile((previous) => ({ ...previous, [key]: value }));
  }

  function renderPhonePreview() {
    return <div className={styles.phoneMock}><div className={styles.phoneScreen}>
      <div className={styles.dynamicIsland} aria-hidden="true" />
      <div className={styles.phoneStatus}><span>9:41</span><span>▮▮▮ ◒ ▰</span></div>
      <h4>Ваша карточка</h4>
      {profile.business_photo_url ? <img className={styles.mockImage} src={profile.business_photo_url} alt="" /> : <div className={styles.mockImage}>Добавьте фото</div>}
      <p className={styles.mockBusinessName}>{profile.company_name || "Ваш бизнес"}</p>
      <p className={styles.mockCategory}>{profile.business_category || "Категория бизнеса"}</p>
      <div className={styles.mockPills} role="tablist"><button type="button" className={previewTab === "services" ? styles.mockPillActive : styles.mockPill} onClick={() => setPreviewTab("services")}>Услуги</button><button type="button" className={previewTab === "about" ? styles.mockPillActive : styles.mockPill} onClick={() => setPreviewTab("about")}>О бизнесе</button></div>
      <div className={styles.phoneContent}>
        {previewTab === "services" ? activeServices.length ? activeServices.map((service) => <article key={service.id} className={styles.clientServiceCard}>{service.image_url ? <img src={service.image_url} alt="" /> : <div className={styles.clientServiceImage} />}<div className={styles.clientServiceBody}><strong>{service.discount_percent > 0 ? `Скидка ${service.discount_percent}%: ${service.name}` : service.name}</strong><p>{service.description || "Описание услуги"}</p><b>{discountedPrice(service)}</b>{service.is_subscription && <span>Доступно по подписке MySub</span>}</div><button type="button" aria-label={`Добавить ${service.name}`} className={addedServiceIds.includes(service.id) ? styles.addedButton : styles.addButton} onClick={() => setAddedServiceIds((items) => items.includes(service.id) ? items.filter((id) => id !== service.id) : [...items, service.id])}>{addedServiceIds.includes(service.id) ? "✓" : "+"}</button></article>) : <p className={styles.phoneEmpty}>Здесь появятся ваши услуги.</p> : <div className={styles.phoneAbout}><p>{profile.description || "Добавьте описание, чтобы клиентам было проще выбрать вас."}</p><strong>{profile.city || "Город"}</strong><p>{profile.address || "Адрес не указан"}</p><p>{profile.working_hours || "График работы не указан"}</p>{profile.website && <a href={profile.website} target="_blank" rel="noreferrer">Сайт</a>}{profile.instagram && <p>{profile.instagram}</p>}</div>}
      </div>
    </div></div>;
  }

  if (isPreviewMode) {
    return (
      <section className={styles.previewPage}>
        <button type="button" className={styles.backToBusinessButton} onClick={() => setIsPreviewMode(false)}>← Назад в мой бизнес</button>
        <div className={styles.previewPhoneStage}>{renderPhonePreview()}</div>
      </section>
    );
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
            <div className={styles.sectionHeaderInline}><div><h3>Услуги для клиентов</h3><p className={styles.sectionHint}>Эти услуги будут показаны клиентам в мобильной карточке.</p></div><Link className={styles.ghostButton} href="/partner/dashboard/manage">Управлять услугами</Link></div>
            {activeServices.length ? <div className={styles.itemList}>{activeServices.map((service) => <article key={service.id} className={styles.listItem}>{service.image_url ? <img src={service.image_url} alt="" /> : <div className={styles.itemPlaceholder} /> }<div><strong>{service.name}</strong><p>{service.description || formatPrice(service.price)}</p></div><span>{formatPrice(service.price)}</span></article>)}</div> : <p className={styles.emptyText}>Добавьте услуги в разделе «Услуги и категории».</p>}
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}><h3>Фотография бизнеса</h3><button type="button" className={styles.ghostButton} onClick={() => profilePhotoInput.current?.click()}>Загрузить фото</button></div>
            <button type="button" className={styles.photoBox} onClick={() => profilePhotoInput.current?.click()}>{profile.business_photo_url ? <img src={profile.business_photo_url} alt="Фотография бизнеса" /> : "Добавить фото"}</button>
            <input ref={profilePhotoInput} className={styles.fileInput} type="file" accept="image/*" onChange={(event) => void handlePhotoChange(event)} />
          </section>
        </div>

        <aside className={styles.previewCard}>
          <span className={styles.previewLabel}>Клиентский вид на iPhone</span>
          <p className={styles.previewText}>Проверьте карточку и услуги так, как их увидит клиент.</p>
          <div className={styles.compactPhonePreview}>{renderPhonePreview()}</div>
          <button type="button" className={styles.openPreviewButton} onClick={() => setIsPreviewMode(true)}>Предпросмотр</button>
        </aside>
      </div>
    </section>
  );
}
