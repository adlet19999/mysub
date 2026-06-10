"use client";

import Image from "next/image";
import { FormEvent } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

export default function PartnerRegisterCredentialsPage() {
  const router = useRouter();

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const getValue = (id: string) => {
      const element = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
      return (element?.value || "").trim();
    };

    const draft = {
      full_name: getValue("full-name"),
      phone: getValue("phone"),
      email: getValue("email"),
      company_name: getValue("company-name"),
      business_category: getValue("business-type"),
      address: getValue("address"),
    };

    if (typeof window !== "undefined") {
      localStorage.setItem("partner_register_draft", JSON.stringify(draft));
    }

    router.push("/partner/register/account");
  }

  return (
    <div className={styles.shell}>
      <div className={styles.panel}>
        <div className={styles.page}>
          <main className={styles.container}>
            <header className={styles.header}>
              <Image src="/logo.svg" alt="MySub" width={132} height={46} priority />
              <p className={styles.subtitle}>Регистрация нового партнера</p>
            </header>

            <div className={styles.steps}>
              <span className={`${styles.step} ${styles.active}`}>1</span>
              <span className={styles.line} />
              <span className={`${styles.step} ${styles.active}`}>2</span>
              <span className={styles.line} />
              <span className={styles.step}>3</span>
              <span className={styles.line} />
              <span className={styles.step}>4</span>
            </div>

            <form className={styles.card} onSubmit={onSubmit}>
              <div className={styles.cardTitle}>Данные компании и партнера</div>

              <div className={styles.section}>
                <div className={styles.sectionTitle}>Данные партнера</div>

            <div className={styles.formGroup}>
              <label htmlFor="full-name">ФИО *</label>
              <input id="full-name" type="text" required />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="position">Должность</label>
              <input id="position" type="text" />
            </div>

            <div className={styles.formRow}>
              <div className={styles.formGroup}>
                <label htmlFor="phone">Телефон *</label>
                <input id="phone" type="tel" required />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="email">Email *</label>
                <input id="email" type="email" required />
              </div>
            </div>

            <label className={styles.uploadBox} htmlFor="partner-logo">
              <input id="partner-logo" type="file" accept="image/*" hidden />
              <div className={styles.uploadBoxInner}>
                <svg
                  className={styles.uploadLogoIcon}
                  width="54"
                  height="54"
                  viewBox="0 0 24 24"
                  fill="none"
                  aria-hidden="true"
                  strokeWidth="1.8"
                >
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <circle cx="8.5" cy="8.5" r="1.5" />
                  <path d="M21 15L16 10L5 21" />
                </svg>
                <div className={styles.uploadText}>Загрузить логотип</div>
              </div>
            </label>
              </div>

              <div className={styles.section}>
                <div className={styles.sectionTitle}>Данные компании</div>

            <div className={styles.formGroup}>
              <label htmlFor="company-name">Наименование компании *</label>
              <input id="company-name" type="text" required />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="business-type">Категория бизнеса *</label>
              <select id="business-type" defaultValue="Кафе и рестораны" required>
                <option value="Кафе и рестораны">Кафе и рестораны</option>
                <option value="Медицинские услуги">Медицинские услуги</option>
                <option value="Спорт">Спорт</option>
                <option value="Автоуслуги">Автоуслуги</option>
                <option value="Кружки и курсы">Кружки и курсы</option>
                <option value="Салон красоты">Салон красоты</option>
                <option value="Досуг">Досуг</option>
              </select>
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="branches">Количество филиалов</label>
              <input id="branches" type="number" min="1" />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="city">Город</label>
              <select id="city" defaultValue="almaty">
                <option value="almaty">Алматы</option>
                <option value="astana">Астана</option>
                <option value="shymkent">Шымкент</option>
              </select>
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="address">Адрес *</label>
              <input id="address" type="text" required />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="work-phone">Рабочий телефон</label>
              <input id="work-phone" type="tel" />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="work-schedule">График работы</label>
              <input id="work-schedule" type="text" placeholder="Пн-Пт: 9:00-20:00, Сб-Вс: 10:00-18:00" />
            </div>
              </div>

              <div className={styles.section}>
                <div className={styles.sectionTitle}>Реквизиты компании</div>

            <div className={styles.formGroup}>
              <label htmlFor="bank-name">Наименование банка</label>
              <input id="bank-name" type="text" />
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="iin-bin">ИИН/БИН</label>
              <input id="iin-bin" type="text" />
            </div>

            <div className={styles.formRowFour}>
              <div className={styles.formGroup}>
                <label htmlFor="bik">БИК</label>
                <input id="bik" type="text" />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="iik">ИИК</label>
                <input id="iik" type="text" />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="kbe">КБЕ</label>
                <input id="kbe" type="text" />
              </div>

              <div className={styles.formGroup}>
                <label htmlFor="knp">КНП</label>
                <input id="knp" type="text" />
              </div>
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="legal-address">Юридический адрес</label>
              <input id="legal-address" type="text" />
            </div>
              </div>

              <div className={styles.documentsHeader}>
                <div className={styles.sectionTitle}>Добавьте документы</div>
                <button className={`${styles.btn} ${styles.btnUpload}`} type="button">
                  + Загрузить документы
                </button>
              </div>

              <label className={styles.uploadDoc} htmlFor="doc-1">
            <input id="doc-1" type="file" hidden />
            <div className={styles.uploadIcon}>+</div>
            <div>Загрузите свидетельство</div>
              </label>

              <label className={styles.uploadDoc} htmlFor="doc-2">
            <input id="doc-2" type="file" hidden />
            <div className={styles.uploadIcon}>+</div>
            <div>Талон о регистрации</div>
              </label>

              <label className={styles.uploadDoc} htmlFor="doc-3">
            <input id="doc-3" type="file" hidden />
            <div className={styles.uploadIcon}>+</div>
            <div>Справка о регистрации компании</div>
              </label>

              <label className={styles.uploadDoc} htmlFor="doc-4">
            <input id="doc-4" type="file" hidden />
            <div className={styles.uploadIcon}>+</div>
            <div>Медицинская лицензия</div>
              </label>

              <div className={styles.actions}>
                <button className={`${styles.btn} ${styles.btnSecondary}`} type="button" onClick={() => router.push("/partner/register")}>
                  Назад
                </button>

                <button className={`${styles.btn} ${styles.btnPrimary}`} type="submit">
                  Продолжить
                </button>
              </div>

              <div className={styles.loginLink}>
                Уже есть аккаунт?{" "}
                <button type="button" onClick={() => router.push("/partner")}>
                  Войти
                </button>
              </div>
            </form>
          </main>

          <footer className={styles.footer}>
            <span>© 2026 MySub. Все права защищены</span>
            <div className={styles.footerLinks}>
              <button type="button">Политика конфиденциальности</button>
              <button type="button">Публичная оферта</button>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
