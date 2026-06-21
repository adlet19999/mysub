"use client";

import { useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type PartnerProfile = {
  full_name: string;
  email: string;
  phone: string;
  company_name: string;
  business_category: string;
  address: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

const DEFAULT_PROFILE: PartnerProfile = {
  full_name: "",
  email: "",
  phone: "",
  company_name: "",
  business_category: "",
  address: "",
};

export default function PartnerBusinessPage() {
  const tenant = TENANT_DEFAULT;
  const [partnerEmail, setPartnerEmail] = useState("");
  const [profile, setProfile] = useState<PartnerProfile>(DEFAULT_PROFILE);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const isSaveDisabled = useMemo(() => {
    return saving || !profile.company_name.trim() || !profile.email.trim() || !profile.phone.trim();
  }, [profile.company_name, profile.email, profile.phone, saving]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) {
      setLoading(false);
      return;
    }
    try {
      const parsed = JSON.parse(raw) as { email?: string; username?: string };
      const email = (parsed.email || parsed.username || "").trim().toLowerCase();
      setPartnerEmail(email);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    async function loadProfile() {
      if (!partnerEmail) {
        return;
      }
      setLoading(true);
      setMessage("");
      try {
        const response = await fetch(`${API_BASE}/partner/profile/`, {
          headers: {
            "Content-Type": "application/json",
            "X-Tenant": tenant,
            "X-Partner-Email": partnerEmail,
          },
          cache: "no-store",
        });
        const payload = (await response.json()) as Partial<PartnerProfile> & { message?: string };
        if (!response.ok) {
          setMessage(payload.message || "Не удалось загрузить профиль");
          return;
        }
        setProfile({
          full_name: (payload.full_name || "").trim(),
          email: (payload.email || "").trim(),
          phone: (payload.phone || "").trim(),
          company_name: (payload.company_name || "").trim(),
          business_category: (payload.business_category || "").trim(),
          address: (payload.address || "").trim(),
        });
      } catch {
        setMessage("Не удалось загрузить профиль");
      } finally {
        setLoading(false);
      }
    }

    void loadProfile();
  }, [partnerEmail, tenant]);

  async function saveProfile() {
    if (!partnerEmail || isSaveDisabled) {
      return;
    }
    setSaving(true);
    setMessage("");
    try {
      const response = await fetch(`${API_BASE}/partner/profile/`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-Tenant": tenant,
          "X-Partner-Email": partnerEmail,
        },
        body: JSON.stringify(profile),
      });
      const payload = (await response.json()) as Partial<PartnerProfile> & { message?: string };
      if (!response.ok) {
        setMessage(payload.message || "Не удалось сохранить профиль");
        return;
      }

      setProfile({
        full_name: (payload.full_name || "").trim(),
        email: (payload.email || "").trim(),
        phone: (payload.phone || "").trim(),
        company_name: (payload.company_name || "").trim(),
        business_category: (payload.business_category || "").trim(),
        address: (payload.address || "").trim(),
      });
      if ((payload.email || "").trim()) {
        setPartnerEmail((payload.email || "").trim().toLowerCase());
      }

      if (typeof window !== "undefined") {
        const raw = localStorage.getItem("partner_auth_user");
        if (raw) {
          try {
            const current = JSON.parse(raw) as Record<string, string>;
            const next = {
              ...current,
              email: payload.email || current.email,
              username: payload.email || current.username,
              phone: payload.phone || current.phone,
              company_name: payload.company_name || current.company_name,
              business_category: payload.business_category || current.business_category,
              address: payload.address || current.address,
            };
            localStorage.setItem("partner_auth_user", JSON.stringify(next));
          } catch {
            // ignore invalid local storage content
          }
        }
      }

      setMessage("Данные бизнеса успешно сохранены");
    } catch {
      setMessage("Не удалось сохранить профиль");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className={styles.page}>
      <div className={styles.headerRow}>
        <div>
          <h2 className={styles.pageTitle}>Мой бизнес</h2>
          <p className={styles.pageSubtitle}>Управление информацией о вашем бизнесе</p>
        </div>
        <button type="button" className={styles.saveTopButton} disabled={isSaveDisabled} onClick={saveProfile}>
          {saving ? "Сохраняем..." : "Сохранить"}
        </button>
      </div>

      {message ? <p className={styles.pageSubtitle}>{message}</p> : null}

      <div className={styles.grid}>
        <div className={styles.leftColumn}>
          <section className={styles.sectionCard}>
            <h3>Основная информация</h3>
            <div className={styles.fieldGrid}>
              <label>
                <span>Название бизнеса</span>
                <input
                  value={profile.company_name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, company_name: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>Основная категория</span>
                <input
                  value={profile.business_category}
                  onChange={(event) => setProfile((prev) => ({ ...prev, business_category: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>Описание</span>
                <textarea defaultValue="" />
              </label>
              <label>
                <span>Город</span>
                <input defaultValue="Алматы" />
              </label>
              <label>
                <span>Адрес</span>
                <input
                  value={profile.address}
                  onChange={(event) => setProfile((prev) => ({ ...prev, address: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>График работы</span>
                <input defaultValue="Пн-Пт: 9:00-20:00, Сб-Вс: 10:00-18:00" />
              </label>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <h3>Контакты</h3>
            <div className={styles.fieldGrid}>
              <label>
                <span>Контактное лицо</span>
                <input
                  value={profile.full_name}
                  onChange={(event) => setProfile((prev) => ({ ...prev, full_name: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>Телефон</span>
                <input
                  value={profile.phone}
                  onChange={(event) => setProfile((prev) => ({ ...prev, phone: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>Email</span>
                <input
                  value={profile.email}
                  onChange={(event) => setProfile((prev) => ({ ...prev, email: event.target.value }))}
                  disabled={loading}
                />
              </label>
              <label>
                <span>Web-сайт</span>
                <input defaultValue="" />
              </label>
              <label>
                <span>Instagram</span>
                <input defaultValue="" />
              </label>
            </div>
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}>
              <h3>Предложения</h3>
              <button type="button" className={styles.ghostButton}>+ Добавить еще</button>
            </div>

            <div className={styles.uploadBox}>Добавить фото</div>
            <label>
              <span>Название услуги</span>
                <input defaultValue="" />
            </label>
            <label>
              <span>Описание</span>
                <textarea defaultValue="" />
            </label>

            <label className={styles.checkboxLabel}>
              <input type="checkbox" defaultChecked />
              <span>Доступно по подписке</span>
            </label>

            <button type="button" className={styles.saveButton}>Сохранить услугу</button>
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}>
              <h3>Столы</h3>
              <button type="button" className={styles.ghostButton}>+ Добавить еще</button>
            </div>

            <div className={styles.uploadBox}>Добавить фото</div>
            <label>
              <span>Название стола</span>
              <input defaultValue="" />
            </label>
            <label>
              <span>Описание</span>
              <textarea defaultValue="" />
            </label>

            <button type="button" className={styles.saveButton}>Сохранить</button>
          </section>

          <section className={styles.sectionCard}>
            <div className={styles.sectionHeaderInline}>
              <h3>Фотография бизнеса</h3>
              <button type="button" className={styles.ghostButton}>+ Загрузить фото</button>
            </div>
            <div className={styles.photoBox}>Добавить фото</div>
          </section>
        </div>

        <aside className={styles.previewCard}>
          <button type="button" className={styles.previewBtn}>Предпросмотр</button>
          <div className={styles.phoneMock}>
            <div className={styles.phoneScreen}>
              <h4>Ваша карточка</h4>
              <div className={styles.mockImage}>Добавить фото</div>
              <p className={styles.mockBusinessName}>{profile.company_name || "Ваш бизнес"}</p>
              <div className={styles.mockPills}>
                <span className={styles.mockPillActive}>Предложения</span>
                <span className={styles.mockPill}>Отзывы(23)</span>
              </div>
              <div className={styles.mockOfferCard}>
                <strong>{profile.business_category || "Категория бизнеса"}</strong>
                <p>{profile.address || "Добавьте адрес вашего бизнеса"}</p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
