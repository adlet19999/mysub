"use client";

import styles from "./page.module.css";

const mockOffers = [
  { id: 1, title: "Скидка на роллы 50%", desc: "Приходите в наше кафейно и получите скидку 50% на любую позицию" },
];

export default function PartnerBusinessPage() {
  return (
    <section className={styles.page}>
      <div className={styles.headerRow}>
        <div>
          <h2 className={styles.pageTitle}>Мой бизнес</h2>
          <p className={styles.pageSubtitle}>Управление информацией о вашем бизнесе</p>
        </div>
        <button type="button" className={styles.saveTopButton}>
          Сохранить
        </button>
      </div>

      <div className={styles.grid}>
        <div className={styles.leftColumn}>
          <section className={styles.sectionCard}>
            <h3>Основная информация</h3>
            <div className={styles.fieldGrid}>
              <label>
                <span>Название бизнеса</span>
                <input defaultValue='Кофейня "Уют"' />
              </label>
              <label>
                <span>Основная категория</span>
                <input defaultValue="Кафе/Рестораны" />
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
                <input defaultValue="ул. Центральная, 22" />
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
                <span>Телефон</span>
                <input defaultValue="+7 (777) 123-45-67" />
              </label>
              <label>
                <span>Email</span>
                <input defaultValue="uuyt@gmail.com" />
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
              <input defaultValue={mockOffers[0].title} />
            </label>
            <label>
              <span>Описание</span>
              <textarea defaultValue={mockOffers[0].desc} />
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
              <p className={styles.mockBusinessName}>Кофейня "Уют"</p>
              <div className={styles.mockPills}>
                <span className={styles.mockPillActive}>Предложения</span>
                <span className={styles.mockPill}>Отзывы(23)</span>
              </div>
              <div className={styles.mockOfferCard}>
                <strong>Скидка на роллы 50%</strong>
                <p>Приходите в наше кафейно и получите скидку 50% на любую позицию</p>
              </div>
            </div>
          </div>
        </aside>
      </div>
    </section>
  );
}
