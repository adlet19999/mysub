"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import partnerStyles from "../../partner/dashboard/layout.module.css";
import styles from "./page.module.css";

type DashboardData = {
  admin: { name: string; email: string };
  metrics: { customers_total: number; subscriptions_active: number; customers_without_subscription: number; customers_turnover: string; partners_total: number; partners_active: number; bookings_total: number; revenue_total: string };
  customers: Array<{ id: number; name: string; email: string; phone: string; city_name: string; created_at: string; visits: number; last_visit: string | null; total_amount: string }>;
  partners: Array<{ id: number; name: string; email: string; category: string; is_active: boolean }>;
};

const navigation = [
  { id: "dashboard", label: "Дашборд", icon: "/statistics.svg" },
  { id: "users", label: "Пользователи", icon: "/specialists.svg" },
  { id: "partners", label: "Партнёры", icon: "/mybusiness.svg" },
  { id: "subscriptions", label: "Подписки", icon: "/subs_icon.svg" },
  { id: "reviews", label: "Отзывы", icon: "/otzyv.svg" },
  { id: "statistics", label: "Статистика", icon: "/statistics.svg" },
  { id: "account", label: "Аккаунт", icon: "/profile.svg" },
];

function formatMoney(value: string) {
  const amount = Number(value);
  return Number.isFinite(amount) ? `${new Intl.NumberFormat("ru-RU").format(amount)} ₸` : "0 ₸";
}

function formatDateTime(value: string | null) {
  if (!value) return "Нет визитов";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Нет визитов"
    : new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

export default function AdminDashboardPage() {
  const router = useRouter();
  const [data, setData] = useState<DashboardData | null>(null);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadDashboard() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/admin/dashboard", { cache: "no-store" });
      if (response.status === 401) {
        router.replace("/admin");
        return;
      }
      const payload = (await response.json()) as DashboardData & { message?: string };
      if (!response.ok) {
        setError(payload.message || "Не удалось загрузить данные");
        return;
      }
      setData(payload);
    } catch {
      setError("Не удалось подключиться к серверу");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadDashboard(); }, []);

  async function logout() {
    await fetch("/api/admin/logout", { method: "POST" });
    router.replace("/admin");
  }

  const tabLabel = navigation.find((item) => item.id === activeTab)?.label || "Дашборд";

  return (
    <main className={partnerStyles.screen}>
      <header className={partnerStyles.header}>
        <div className={partnerStyles.logoCell}><img src="/logo.svg" alt="MySub" className={partnerStyles.logoImage} /></div>
        <div className={partnerStyles.headerMain}><h1 className={partnerStyles.headerTitle}>Дашборд</h1><p className={partnerStyles.headerSubtitle}>Админ</p></div>
        <div className={partnerStyles.headerActions}><button className={partnerStyles.notifyButton} aria-label="Уведомления"><img src="/notifications.svg" alt="" /></button><div className={partnerStyles.avatarPill}>{(data?.admin.name || "A").slice(0, 1).toUpperCase()}</div></div>
      </header>
      <aside className={partnerStyles.sidebar}>
        <nav className={partnerStyles.menuTop} aria-label="Административная навигация">
          {navigation.map(({ id, label, icon }) => <button key={id} onClick={() => setActiveTab(id)} className={`${partnerStyles.sideItem} ${activeTab === id ? partnerStyles.sideItemActive : ""}`}><img src={icon} alt="" className={partnerStyles.sideIcon} aria-hidden /><span>{label}</span></button>)}
        </nav>
        <div className={partnerStyles.menuBottom}><button className={partnerStyles.sideItem} onClick={() => void logout()}><img src="/quit.svg" alt="" className={partnerStyles.sideIcon} aria-hidden /><span>Выйти</span></button></div>
      </aside>
      <section className={partnerStyles.contentArea}>
        <div className={styles.content}>
          {loading ? <div className={styles.state}>Загружаем данные панели...</div> : null}
          {!loading && error ? <div className={styles.state}><p>{error}</p><button onClick={() => void loadDashboard()}><img src="/change.svg" alt="" /> Повторить</button></div> : null}
          {!loading && !error && data ? <TabContent activeTab={activeTab} data={data} onOpenUsers={() => setActiveTab("users")} /> : null}
        </div>
      </section>
    </main>
  );
}

function TabContent({ activeTab, data, onOpenUsers }: { activeTab: string; data: DashboardData; onOpenUsers: () => void }) {
  if (activeTab === "users") return <UsersTable customers={data.customers} />;
  if (activeTab === "partners") return <PartnersTable partners={data.partners} />;
  if (activeTab === "account") return <section><h1>Аккаунт</h1><div className={styles.account}><img src="/profile.svg" alt="" /><div><strong>{data.admin.name}</strong><span>{data.admin.email || "Администратор MySub"}</span></div></div></section>;
  if (activeTab !== "dashboard") return <section><h1>{navigation.find((item) => item.id === activeTab)?.label}</h1><div className={styles.empty}>В этом разделе пока нет данных.</div></section>;
  return <>
    <div className={styles.titleRow}><div><h1>Дашборд</h1><p>Админ</p></div></div>
    <section className={styles.metrics}>
      <Metric label="Всего клиентов" value={data.metrics.customers_total.toString()} />
      <Metric label="Активные подписки" value={data.metrics.subscriptions_active.toString()} />
      <Metric label="Без подписки" value={data.metrics.customers_without_subscription.toString()} />
      <Metric label="Оборот клиентов" value={formatMoney(data.metrics.customers_turnover)} />
    </section>
    <section className={styles.partnerMetrics}><h2>Партнёры</h2><div><Metric label="Всего партнёров" value={data.metrics.partners_total.toString()} /><Metric label="Активных" value={data.metrics.partners_active.toString()} /></div></section>
    <CustomersTable customers={data.customers} onOpenUsers={onOpenUsers} />
  </>;
}

function Metric({ label, value }: { label: string; value: string }) {
  return <article className={styles.metric}><div><p>{label}</p><strong>{value}</strong></div></article>;
}

function UsersTable({ customers, compact = false }: { customers: DashboardData["customers"]; compact?: boolean }) {
  return <section className={styles.tableSection}><div className={styles.sectionHead}><div><h2>{compact ? "Новые пользователи" : "Пользователи"}</h2><p>{compact ? "Последние регистрации" : "Клиенты мобильного приложения"}</p></div>{compact ? <button>Все пользователи</button> : null}</div>{customers.length ? <div className={styles.table}><div className={styles.tableHeader}><span>Пользователь</span><span>Город</span><span>Телефон</span></div>{customers.map((customer) => <div className={styles.tableRow} key={customer.id}><span><b>{customer.name}</b><small>{customer.email}</small></span><span>{customer.city_name || "Не указан"}</span><span>{customer.phone}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}</section>;
}

function CustomersTable({ customers, onOpenUsers }: { customers: DashboardData["customers"]; onOpenUsers: () => void }) {
  return <section className={styles.customersSection}>
    <h2>Пользователи</h2>
    {customers.length ? <div className={styles.customerTable}><div className={styles.customerTableHeader}><span>ФИО пользователей</span><span>Телефон</span><span>Подписка</span><span>Последний визит</span><span>Визиты</span><span>Сумма</span></div>{customers.map((customer) => <div className={styles.customerTableRow} key={customer.id}><span className={styles.customerIdentity}><i>{customer.name.slice(0, 1).toUpperCase()}</i><span><b>{customer.name}</b><small>{customer.email || "Email не указан"}</small></span></span><span>{customer.phone}</span><span className={styles.noSubscription}>Нет</span><span>{formatDateTime(customer.last_visit)}</span><span>{customer.visits}</span><span>{formatMoney(customer.total_amount)}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}
    <button className={styles.allUsersButton} onClick={onOpenUsers}>Все пользователи</button>
  </section>;
}

function PartnersTable({ partners, compact = false }: { partners: DashboardData["partners"]; compact?: boolean }) {
  return <section className={styles.tableSection}><div className={styles.sectionHead}><div><h2>{compact ? "Партнёры" : "Партнёры"}</h2><p>{compact ? "Недавно добавленные компании" : "Компании в системе MySub"}</p></div>{compact ? <button>Все партнёры</button> : null}</div>{partners.length ? <div className={styles.table}><div className={styles.tableHeader}><span>Компания</span><span>Категория</span><span>Статус</span></div>{partners.map((partner) => <div className={styles.tableRow} key={partner.id}><span><b>{partner.name}</b><small>{partner.email}</small></span><span>{partner.category || "Не указана"}</span><span><i className={partner.is_active ? styles.statusActive : styles.statusInactive} />{partner.is_active ? "Активен" : "Отключён"}</span></div>)}</div> : <div className={styles.empty}>Партнёров пока нет.</div>}</section>;
}