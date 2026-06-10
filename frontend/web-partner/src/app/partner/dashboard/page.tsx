"use client";

import styles from "./page.module.css";

const iconCalendar = "/calendar.svg";

type RowItem = {
  date: string;
  client: string;
  phone: string;
  service: string;
  status: string;
  subscription: string;
  sum: string;
};

const stats = [
  { label: "Всего записей", value: "5" },
  { label: "Завершено", value: "4" },
  { label: "Выручка", value: "67 500 ₸" },
];

const rows: RowItem[] = [
  {
    date: "15 мар. 2025, 10:00",
    client: "Петрова Мария",
    phone: "+7 (707) 111-22-33",
    service: "Стрижка мужская",
    status: "Завершена",
    subscription: "Активна",
    sum: "1 500 ₸",
  },
  {
    date: "15 мар. 2025, 11:00",
    client: "Смирнова Анна",
    phone: "+7 (775) 333-44-55",
    service: "Окрашивание волос",
    status: "Завершена",
    subscription: "Нет",
    sum: "25 500 ₸",
  },
  {
    date: "15 мар. 2025, 14:00",
    client: "Иванова Елена",
    phone: "+7 (702) 666-77-88",
    service: "Групповой мастер-класс",
    status: "Завершена",
    subscription: "Активна",
    sum: "10 000 ₸",
  },
  {
    date: "14 мар. 2025, 10:00",
    client: "Николаев Алексей",
    phone: "+7 (708) 888-99-00",
    service: "Стрижка мужская",
    status: "Неявка",
    subscription: "Активна",
    sum: "-",
  },
  {
    date: "14 мар. 2025, 15:00",
    client: "Козлова Ольга",
    phone: "+7 (708) 222-33-44",
    service: "Маникюр, Педикюр",
    status: "Завершена",
    subscription: "Нет",
    sum: "30 500 ₸",
  },
];

function Badge({ value, type }: { value: string; type: "status" | "subscription" }) {
  const className =
    type === "status"
      ? value === "Неявка"
        ? styles.badgeDanger
        : styles.badgeSuccess
      : value === "Активна"
        ? styles.badgeSuccess
        : styles.badgeMuted;

  return <span className={className}>{value}</span>;
}

export default function PartnerDashboardPage() {
  return (
    <section className={styles.content}>
      <div className={styles.contentHeading}>
        <h2 className={styles.pageTitle}>Статистика</h2>
        <p className={styles.pageSubtitle}>Аналитика записей и выгрузка данных</p>
      </div>

      <section className={styles.statsRow}>
        {stats.map((item) => (
          <article key={item.label} className={styles.statCard}>
            <p>{item.label}</p>
            <strong>{item.value}</strong>
          </article>
        ))}
      </section>

      <section className={styles.filtersBox}>
        <div className={styles.filterInputs}>
          <label className={styles.inputGroup}>
            <span>Период с</span>
            <div className={styles.dateInput}>
              <img src={iconCalendar} alt="" className={styles.calendarIcon} aria-hidden />
              <span>15.04.2026</span>
            </div>
          </label>
          <label className={styles.inputGroup}>
            <span>Период по</span>
            <div className={styles.dateInput}>
              <img src={iconCalendar} alt="" className={styles.calendarIcon} aria-hidden />
              <span>30.04.2026</span>
            </div>
          </label>
        </div>

        <div className={styles.filterActions}>
          <button type="button" className={styles.applyButton}>
            Применить фильтры
          </button>
          <button type="button" className={styles.exportButton}>
            Выгрузить в Excel
          </button>
        </div>
      </section>

      <div className={styles.tableBox}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.wDate}>Дата и время</th>
              <th>ФИО клиента</th>
              <th>Телефон</th>
              <th>Услуги</th>
              <th className={styles.wStatus}>Статус</th>
              <th className={styles.wStatus}>Подписка</th>
              <th className={styles.wSum}>Сумма</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={`${row.date}-${row.phone}`}>
                <td>{row.date}</td>
                <td>{row.client}</td>
                <td>{row.phone}</td>
                <td>{row.service}</td>
                <td className={styles.center}>
                  <Badge value={row.status} type="status" />
                </td>
                <td className={styles.center}>
                  <Badge value={row.subscription} type="subscription" />
                </td>
                <td>{row.sum}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
