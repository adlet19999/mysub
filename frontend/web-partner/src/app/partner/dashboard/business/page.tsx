"use client";

import { ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import { Eye } from "lucide-react";
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
  business_photo_urls: string[];
};

type BusinessOffer = {
  id: number;
  title: string;
  description: string;
  photo_url: string;
  photo_urls: string[];
  is_subscription: boolean;
  is_active: boolean;
  display_order: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
const EMPTY_PROFILE: PartnerProfile = {
  full_name: "", email: "", phone: "", company_name: "", business_category: "", address: "",
  description: "", city: "", working_hours: "", website: "", instagram: "", business_photo_url: "", business_photo_urls: [],
};

export default function PartnerBusinessPage() {
  const [partnerEmail, setPartnerEmail] = useState("");
  const [profile, setProfile] = useState<PartnerProfile>(EMPTY_PROFILE);
  const [offers, setOffers] = useState<BusinessOffer[]>([]);
  const [offerTitle, setOfferTitle] = useState("");
  const [offerDescription, setOfferDescription] = useState("");
  const [offerPhotos, setOfferPhotos] = useState<string[]>([]);
  const [offerSubscription, setOfferSubscription] = useState(false);
  const [isSavingOffer, setIsSavingOffer] = useState(false);
  const [isOfferEditorOpen, setIsOfferEditorOpen] = useState(false);
  const [editingOfferId, setEditingOfferId] = useState<number | null>(null);
  const [draggedOfferId, setDraggedOfferId] = useState<number | null>(null);
  const [draggedBusinessPhotoIndex, setDraggedBusinessPhotoIndex] = useState<number | null>(null);
  const [offerError, setOfferError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [isPreviewMode, setIsPreviewMode] = useState(false);
  const [previewTab, setPreviewTab] = useState<"offers" | "reviews">("offers");
  const [addedServiceIds, setAddedServiceIds] = useState<number[]>([]);
  const profilePhotoInput = useRef<HTMLInputElement>(null);
  const offerPhotoInput = useRef<HTMLInputElement>(null);
  const offerTitleInput = useRef<HTMLInputElement>(null);

  const isSaveDisabled = useMemo(() => saving || !profile.company_name.trim() || !profile.email.trim() || !profile.phone.trim(), [profile, saving]);
  const activeOffers = useMemo(() => offers.filter((offer) => offer.is_active), [offers]);

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
      const [profileResponse, offersResponse] = await Promise.all([
        api("/partner/profile/"), api("/partner/business-offers/"),
      ]);
      const profilePayload = (await profileResponse.json()) as Partial<PartnerProfile> & { message?: string };
      const offersPayload = (await offersResponse.json()) as BusinessOffer[];
      if (!profileResponse.ok) throw new Error(profilePayload.message || "Не удалось загрузить профиль");
      setProfile({ ...EMPTY_PROFILE, ...profilePayload });
      setOffers(Array.isArray(offersPayload) ? offersPayload : []);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить данные бизнеса");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadBusiness(); }, [partnerEmail]);

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    try {
      const availableSlots = 8 - profile.business_photo_urls.length;
      if (availableSlots <= 0) {
        setError("Можно добавить не более 8 фотографий бизнеса");
        return;
      }
      const images = await Promise.all(files.slice(0, availableSlots).map((file) => compressImageFileToDataUrl(file, { maxWidth: 1280, maxHeight: 960 })));
      setProfile((previous) => {
        const business_photo_urls = [...previous.business_photo_urls, ...images];
        return { ...previous, business_photo_urls, business_photo_url: business_photo_urls[0] || "" };
      });
    } catch {
      setError("Не удалось обработать изображение");
    } finally {
      event.target.value = "";
    }
  }

  function moveBusinessPhoto(targetIndex: number) {
    if (draggedBusinessPhotoIndex === null || draggedBusinessPhotoIndex === targetIndex) return;
    setProfile((previous) => {
      const business_photo_urls = [...previous.business_photo_urls];
      const [photo] = business_photo_urls.splice(draggedBusinessPhotoIndex, 1);
      business_photo_urls.splice(targetIndex, 0, photo);
      return { ...previous, business_photo_urls, business_photo_url: business_photo_urls[0] || "" };
    });
    setDraggedBusinessPhotoIndex(null);
  }

  async function handleOfferPhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    try {
      const availableSlots = 8 - offerPhotos.length;
      if (availableSlots <= 0) {
        setOfferError("Можно добавить не более 8 фотографий.");
        return;
      }
      const compressedPhotos = await Promise.all(files.slice(0, availableSlots).map((file) => compressImageFileToDataUrl(file, { maxWidth: 1280, maxHeight: 960 })));
      setOfferPhotos((photos) => [...photos, ...compressedPhotos]);
      setOfferError("");
    } catch {
      setError("Не удалось обработать изображение предложения");
    } finally {
      event.target.value = "";
    }
  }

  async function createOffer() {
    if (!partnerEmail) {
      setOfferError("Не удалось определить аккаунт партнера. Обновите страницу и войдите снова.");
      return;
    }
    if (!offerTitle.trim()) {
      setOfferError("Введите название предложения.");
      offerTitleInput.current?.focus();
      return;
    }
    if (isSavingOffer) return;
    setIsSavingOffer(true);
    setError("");
    setOfferError("");
    try {
      const response = await api("/partner/business-offers/", { method: "POST", body: JSON.stringify({ title: offerTitle.trim(), description: offerDescription.trim(), photo_base64_list: offerPhotos, is_subscription: offerSubscription }) });
      const payload = (await response.json()) as BusinessOffer & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось добавить предложение");
      setOffers((items) => [...items, payload]);
      setOfferTitle(""); setOfferDescription(""); setOfferPhotos([]); setOfferSubscription(false);
      setIsOfferEditorOpen(false);
      setEditingOfferId(null);
    } catch (offerError) {
      setOfferError(offerError instanceof Error ? offerError.message : "Не удалось добавить предложение");
    } finally {
      setIsSavingOffer(false);
    }
  }

  function startNewOffer() {
    setOfferTitle("");
    setOfferDescription("");
    setOfferPhotos([]);
    setOfferSubscription(false);
    setOfferError("");
    setEditingOfferId(null);
    setIsOfferEditorOpen(true);
    requestAnimationFrame(() => offerTitleInput.current?.focus());
  }

  function startEditOffer(offer: BusinessOffer) {
    setOfferTitle(offer.title);
    setOfferDescription(offer.description);
    setOfferPhotos(offer.photo_urls);
    setOfferSubscription(offer.is_subscription);
    setOfferError("");
    setEditingOfferId(offer.id);
    setIsOfferEditorOpen(true);
    requestAnimationFrame(() => offerTitleInput.current?.focus());
  }

  async function saveOffer() {
    if (editingOfferId === null) {
      await createOffer();
      return;
    }
    if (!partnerEmail) return;
    if (!offerTitle.trim()) {
      setOfferError("Введите название предложения.");
      offerTitleInput.current?.focus();
      return;
    }
    setIsSavingOffer(true);
    setOfferError("");
    try {
      const existingPhotoUrls = offerPhotos.filter((photo) => !photo.startsWith("data:image/"));
      const newPhotoPayloads = offerPhotos.filter((photo) => photo.startsWith("data:image/"));
      const response = await api(`/partner/business-offers/${editingOfferId}/`, { method: "PATCH", body: JSON.stringify({ title: offerTitle.trim(), description: offerDescription.trim(), is_subscription: offerSubscription, photo_urls: existingPhotoUrls, photo_base64_list: newPhotoPayloads }) });
      const payload = (await response.json()) as BusinessOffer & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось сохранить предложение");
      setOffers((items) => items.map((offer) => offer.id === payload.id ? payload : offer));
      setOfferTitle(""); setOfferDescription(""); setOfferPhotos([]); setOfferSubscription(false);
      setIsOfferEditorOpen(false); setEditingOfferId(null);
    } catch (saveError) {
      setOfferError(saveError instanceof Error ? saveError.message : "Не удалось сохранить предложение");
    } finally {
      setIsSavingOffer(false);
    }
  }

  async function deleteOffer(offerId: number) {
    if (!partnerEmail) return;
    try {
      const response = await api(`/partner/business-offers/${offerId}/`, { method: "DELETE" });
      if (!response.ok) throw new Error("Не удалось удалить предложение");
      setOffers((items) => items.filter((offer) => offer.id !== offerId));
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Не удалось удалить предложение");
    }
  }

  async function reorderOffers(nextOffers: BusinessOffer[]) {
    if (!partnerEmail) return;
    const previousOffers = offers;
    setOffers(nextOffers);
    setError("");
    try {
      const response = await api("/partner/business-offers/reorder/", { method: "POST", body: JSON.stringify({ ordered_ids: nextOffers.map((offer) => offer.id) }) });
      const payload = (await response.json()) as BusinessOffer[] | { message?: string };
      if (!response.ok || !Array.isArray(payload)) throw new Error("message" in payload ? payload.message || "Не удалось изменить порядок" : "Не удалось изменить порядок");
      setOffers(payload);
    } catch (moveError) {
      setOffers(previousOffers);
      setError(moveError instanceof Error ? moveError.message : "Не удалось изменить порядок");
    }
  }

  function handleOfferDrop(targetOfferId: number) {
    if (draggedOfferId === null || draggedOfferId === targetOfferId) return;
    const fromIndex = offers.findIndex((offer) => offer.id === draggedOfferId);
    const toIndex = offers.findIndex((offer) => offer.id === targetOfferId);
    if (fromIndex < 0 || toIndex < 0) return;
    const nextOffers = [...offers];
    const [draggedOffer] = nextOffers.splice(fromIndex, 1);
    nextOffers.splice(toIndex, 0, draggedOffer);
    setDraggedOfferId(null);
    void reorderOffers(nextOffers);
  }

  async function saveProfile() {
    if (!partnerEmail || isSaveDisabled) return;
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const { business_photo_url: _businessPhotoUrl, business_photo_urls, ...profileFields } = profile;
      const body = {
        ...profileFields,
        business_photo_urls: business_photo_urls.filter((photo) => !photo.startsWith("data:image/")),
        business_photo_base64_list: business_photo_urls.filter((photo) => photo.startsWith("data:image/")),
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
    return <div className={styles.phoneMock}>
      <span className={styles.phoneMuteButton} aria-hidden="true" /><span className={styles.phoneVolumeUpButton} aria-hidden="true" /><span className={styles.phoneVolumeDownButton} aria-hidden="true" /><span className={styles.phonePowerButton} aria-hidden="true" />
      <div className={styles.phoneScreen}>
      <div className={styles.dynamicIsland} aria-hidden="true"><span /></div>
      <div className={styles.phoneStatus}><span>9:41</span><div className={styles.phoneIndicators} aria-hidden="true"><span className={styles.signalIndicator} /><span className={styles.wifiIndicator} /><span className={styles.batteryIndicator} /></div></div>
      <h4>Ваша карточка</h4>
      {profile.business_photo_urls[0] || profile.business_photo_url ? <img className={styles.mockImage} src={profile.business_photo_urls[0] || profile.business_photo_url} alt="" /> : <div className={styles.mockImage}>Добавьте фото</div>}
      <p className={styles.mockBusinessName}>{profile.company_name || "Ваш бизнес"}</p>
      <p className={styles.mockCategory}>{profile.business_category || "Категория бизнеса"}</p>
      <div className={styles.mockPills} role="tablist"><button type="button" className={previewTab === "offers" ? styles.mockPillActive : styles.mockPill} onClick={() => setPreviewTab("offers")}>Предложения</button><button type="button" className={previewTab === "reviews" ? styles.mockPillActive : styles.mockPill} onClick={() => setPreviewTab("reviews")}>Отзывы</button></div>
      <div className={styles.phoneContent}>
        {previewTab === "offers" ? activeOffers.length ? activeOffers.map((offer) => <article key={offer.id} className={styles.clientServiceCard}>{offer.photo_urls.length ? <div className={styles.offerPhotoCarousel}>{offer.photo_urls.map((photoUrl, index) => <img key={`${photoUrl}-${index}`} src={photoUrl} alt={`${offer.title}, фото ${index + 1}`} />)}</div> : <div className={styles.clientServiceImage} />}<div className={styles.clientServiceBody}><strong>{offer.title}</strong><p>{offer.description || "Описание предложения"}</p>{offer.is_subscription && <span>Доступно по подписке MySub</span>}</div><button type="button" aria-label={`Добавить ${offer.title}`} className={addedServiceIds.includes(offer.id) ? styles.addedButton : styles.addButton} onClick={() => setAddedServiceIds((items) => items.includes(offer.id) ? items.filter((id) => id !== offer.id) : [...items, offer.id])}>{addedServiceIds.includes(offer.id) ? "✓" : "+"}</button></article>) : <p className={styles.phoneEmpty}>Добавьте первое предложение для клиентов.</p> : <p className={styles.phoneEmpty}>Отзывов пока нет.</p>}
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

          <section className={`${styles.sectionCard} ${styles.offersSection}`}>
            <div className={styles.offersHeader}><h3>Предложение</h3><button type="button" className={styles.addOfferButton} onClick={startNewOffer}>+&nbsp; Добавить еще</button></div>
            <input ref={offerPhotoInput} className={styles.fileInput} type="file" accept="image/*" multiple onChange={(event) => void handleOfferPhotoChange(event)} />
            {(isOfferEditorOpen || offers.length === 0) && <article className={styles.offerEditorCard}>
              <button type="button" className={styles.offerPhotoButton} onClick={() => offerPhotoInput.current?.click()}><span className={styles.offerPhotoPlaceholder}><img src="/photo.svg" alt="" aria-hidden />{offerPhotos.length ? "Добавить еще фото" : "Добавить фото"}</span></button>
              {offerPhotos.length ? <div className={styles.offerPhotoList}>{offerPhotos.map((photo, index) => <div key={`${photo}-${index}`} className={styles.offerPhotoPreview}><img src={photo} alt={`Выбранное изображение ${index + 1}`} /><button type="button" onClick={() => setOfferPhotos((photos) => photos.filter((_, photoIndex) => photoIndex !== index))} aria-label={`Удалить фото ${index + 1}`}><img src="/delete.svg" alt="" aria-hidden /></button></div>)}</div> : null}
              <label><span>Название услуги</span><input ref={offerTitleInput} value={offerTitle} onChange={(event) => setOfferTitle(event.target.value)} placeholder="Например, дегустационное меню" /></label>
              <label><span>Описание</span><textarea value={offerDescription} onChange={(event) => setOfferDescription(event.target.value)} placeholder="Расскажите клиентам о предложении" /></label>
              <label className={styles.offerSubscriptionLabel}><input type="checkbox" checked={offerSubscription} onChange={(event) => setOfferSubscription(event.target.checked)} /> <span>Доступно по подписке</span></label>
              {offerError && <p className={styles.offerError}>{offerError}</p>}
              <div className={styles.offerEditorActions}><button type="button" className={styles.saveOfferButton} disabled={isSavingOffer} onClick={() => void saveOffer()}>{isSavingOffer ? "Сохраняем..." : editingOfferId === null ? "Сохранить услугу" : "Сохранить изменения"}</button></div>
            </article>}
            {offers.length ? <div className={styles.savedOfferList}>{offers.map((offer) => <article key={offer.id} className={`${styles.savedOfferCard} ${draggedOfferId === offer.id ? styles.savedOfferCardDragging : ""}`} draggable onDragStart={() => setDraggedOfferId(offer.id)} onDragEnd={() => setDraggedOfferId(null)} onDragOver={(event) => event.preventDefault()} onDrop={() => handleOfferDrop(offer.id)}>{offer.photo_url ? <img src={offer.photo_url} alt="" /> : <div className={styles.itemPlaceholder} />}<div><strong>{offer.title}</strong><p>{offer.description || "Без описания"}</p>{offer.is_subscription && <span>Доступно по подписке</span>}</div><div className={styles.offerCardActions}><button type="button" className={styles.dragHandle} aria-label={`Перетащить ${offer.title}`}>⠿</button><button type="button" className={styles.editOfferButton} onClick={() => startEditOffer(offer)} aria-label={`Редактировать ${offer.title}`}><img src="/change.svg" alt="" className={styles.editOfferIcon} aria-hidden /></button><button type="button" className={styles.offerIconButton} onClick={() => void deleteOffer(offer.id)} aria-label={`Удалить ${offer.title}`}><img src="/delete.svg" alt="" aria-hidden /></button></div></article>)}</div> : null}
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}><h3>Фотографии бизнеса</h3><button type="button" className={styles.ghostButton} onClick={() => profilePhotoInput.current?.click()}>+ Загрузить фото</button></div>
            <div className={styles.businessPhotoGrid}>
              {profile.business_photo_urls.map((photo, index) => <div key={`${photo}-${index}`} className={`${styles.businessPhotoPreview} ${draggedBusinessPhotoIndex === index ? styles.businessPhotoPreviewDragging : ""}`} draggable onDragStart={(event) => { event.dataTransfer.effectAllowed = "move"; setDraggedBusinessPhotoIndex(index); }} onDragEnd={() => setDraggedBusinessPhotoIndex(null)} onDragOver={(event) => event.preventDefault()} onDrop={() => moveBusinessPhoto(index)}><img src={photo} alt={`Фотография бизнеса ${index + 1}`} />{index === 0 && <span className={styles.businessPhotoCover}>Обложка</span>}<button type="button" onClick={() => setProfile((previous) => { const business_photo_urls = previous.business_photo_urls.filter((_, photoIndex) => photoIndex !== index); return { ...previous, business_photo_urls, business_photo_url: business_photo_urls[0] || "" }; })} aria-label={`Удалить фото ${index + 1}`}><img src="/delete.svg" alt="" aria-hidden /></button></div>)}
              {profile.business_photo_urls.length < 8 && <button type="button" className={styles.addBusinessPhotoButton} onClick={() => profilePhotoInput.current?.click()}><img src="/photo.svg" alt="" aria-hidden /><span>Добавить фото</span></button>}
            </div>
            <input ref={profilePhotoInput} className={styles.fileInput} type="file" accept="image/*" multiple onChange={(event) => void handlePhotoChange(event)} />
          </section>
        </div>

        <aside className={styles.previewCard}>
          <button type="button" className={styles.openPreviewButton} onClick={() => setIsPreviewMode(true)}><Eye size={18} strokeWidth={2} aria-hidden="true" />Предпросмотр</button>
          <div className={styles.compactPhonePreview}>{renderPhonePreview()}</div>
        </aside>
      </div>
    </section>
  );
}
