"use client";

import {
  BarChart3,
  Bell,
  Building2,
  CalendarDays,
  ChevronDown,
  LayoutDashboard,
  LogOut,
  MessageSquareText,
  RefreshCw,
  ShieldCheck,
  UserRound,
  UsersRound,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import styles from "./page.module.css";

type DashboardData = {
  admin: { name: string; email: string };
  metrics: { customers_total: number; partners_total: number; partners_active: number; bookings_total: number; revenue_total: string };
  customers: Array<{ id: number; name: string; email: string; phone: string; city_name: string; created_at: string }>;
  partners: Array<{ id: number; name: string; email: string; category: string; is_active: boolean }>;
};

const navigation = [
  { id: "dashboard", label: "Дашборд", icon: LayoutDashboard },
  { id: "users", label: "Пользователи", icon: UsersRound },
  { id: "partners", label: "Партнёры", icon: Building2 },
  { id: "subscriptions", label: "Подписки", icon: CalendarDays },
  { id: "reviews", label: "Отзывы", icon: MessageSquareText },
  { id: "statistics", label: "Статистика", icon: BarChart3 },
  { id: "account", label: "Аккаунт", icon: UserRound },
];

function formatMoney(value: string) {
  const amount = Number(value);
  return Number.isFinite(amount) ? `${new Intl.NumberFormat("ru-RU").format(amount)} ₸` : "0 ₸";
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
    <main className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}><span className={styles.mark}>M</span><span>MySub</span></div>
        <nav aria-label="Административная навигация">
          {navigation.map(({ id, label, icon: Icon }) => (
            <button key={id} onClick={() => setActiveTab(id)} className={activeTab === id ? styles.activeNav : styles.navItem}>
              <Icon size={19} aria-hidden /> <span>{label}</span>
            </button>
          ))}
        </nav>
        <button className={styles.logout} onClick={() => void logout()}><LogOut size={19} aria-hidden /> <span>Выйти</span></button>
      </aside>
      <section className={styles.content}>
        <header className={styles.header}>
          <div className={styles.breadcrumb}>Главная <span>/</span> {tabLabel}</div>
          <div className={styles.headerActions}>
            <button className={styles.iconButton} aria-label="Уведомления"><Bell size={20} /></button>
            <div className={styles.adminName}><span>{data?.admin.name || "Администратор"}</span><small>{data?.admin.email || ""}</small></div>
            <div className={styles.avatar}>{(data?.admin.name || "A").slice(0, 1).toUpperCase()}</div>
            <ChevronDown size={17} className={styles.chevron} />
          </div>
        </header>
        <div className={styles.body}>
          {loading ? <div className={styles.state}>Загружаем данные панели...</div> : null}
          {!loading && error ? <div className={styles.state}><p>{error}</p><button onClick={() => void loadDashboard()}><RefreshCw size={16} /> Повторить</button></div> : null}
          {!loading && !error && data ? <TabContent activeTab={activeTab} data={data} /> : null}
        </div>
      </section>
    </main>
  );
}

function TabContent({ activeTab, data }: { activeTab: string; data: DashboardData }) {
  if (activeTab === "users") return <UsersTable customers={data.customers} />;
  if (activeTab === "partners") return <PartnersTable partners={data.partners} />;
  if (activeTab === "account") return <section><h1>Аккаунт</h1><div className={styles.account}><ShieldCheck size={23} /><div><strong>{data.admin.name}</strong><span>{data.admin.email || "Администратор MySub"}</span></div></div></section>;
  if (activeTab !== "dashboard") return <section><h1>{navigation.find((item) => item.id === activeTab)?.label}</h1><div className={styles.empty}>В этом разделе пока нет данных.</div></section>;
  return <>
    <div className={styles.titleRow}><div><h1>Дашборд</h1><p>Обзор работы платформы MySub</p></div><button className={styles.period}><CalendarDays size={17} /> За всё время <ChevronDown size={16} /></button></div>
    <section className={styles.metrics}>
      <Metric label="Пользователи" value={data.metrics.customers_total.toString()} icon={<UsersRound size={23} />} tone="mint" />
      <Metric label="Партнёры" value={data.metrics.partners_total.toString()} suffix={`${data.metrics.partners_active} активных`} icon={<Building2 size={23} />} tone="yellow" />
      <Metric label="Бронирования" value={data.metrics.bookings_total.toString()} icon={<CalendarDays size={23} />} tone="blue" />
      <Metric label="Выручка" value={formatMoney(data.metrics.revenue_total)} icon={<BarChart3 size={23} />} tone="pink" />
    </section>
    <section className={styles.grid}><UsersTable customers={data.customers} compact /><PartnersTable partners={data.partners} compact /></section>
  </>;
}

function Metric({ label, value, suffix, icon, tone }: { label: string; value: string; suffix?: string; icon: React.ReactNode; tone: string }) {
  return <article className={styles.metric}><div className={`${styles.metricIcon} ${styles[tone]}`}>{icon}</div><div><p>{label}</p><strong>{value}</strong>{suffix ? <small>{suffix}</small> : null}</div></article>;
}

function UsersTable({ customers, compact = false }: { customers: DashboardData["customers"]; compact?: boolean }) {
  return <section className={styles.tableSection}><div className={styles.sectionHead}><div><h2>{compact ? "Новые пользователи" : "Пользователи"}</h2><p>{compact ? "Последние регистрации" : "Клиенты мобильного приложения"}</p></div>{compact ? <button>Все пользователи</button> : null}</div>{customers.length ? <div className={styles.table}><div className={styles.tableHeader}><span>Пользователь</span><span>Город</span><span>Телефон</span></div>{customers.map((customer) => <div className={styles.tableRow} key={customer.id}><span><b>{customer.name}</b><small>{customer.email}</small></span><span>{customer.city_name || "Не указан"}</span><span>{customer.phone}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}</section>;
}

function PartnersTable({ partners, compact = false }: { partners: DashboardData["partners"]; compact?: boolean }) {
  return <section className={styles.tableSection}><div className={styles.sectionHead}><div><h2>{compact ? "Партнёры" : "Партнёры"}</h2><p>{compact ? "Недавно добавленные компании" : "Компании в системе MySub"}</p></div>{compact ? <button>Все партнёры</button> : null}</div>{partners.length ? <div className={styles.table}><div className={styles.tableHeader}><span>Компания</span><span>Категория</span><span>Статус</span></div>{partners.map((partner) => <div className={styles.tableRow} key={partner.id}><span><b>{partner.name}</b><small>{partner.email}</small></span><span>{partner.category || "Не указана"}</span><span><i className={partner.is_active ? styles.statusActive : styles.statusInactive} />{partner.is_active ? "Активен" : "Отключён"}</span></div>)}</div> : <div className={styles.empty}>Партнёров пока нет.</div>}</section>;
}