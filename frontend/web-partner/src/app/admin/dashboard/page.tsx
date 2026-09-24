"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { Eye, LockKeyhole, UnlockKeyhole } from "lucide-react";
import partnerStyles from "../../partner/dashboard/layout.module.css";
import styles from "./page.module.css";

type DashboardData = {
  admin: { name: string; email: string };
  metrics: { customers_total: number; subscriptions_active: number; customers_without_subscription: number; customers_turnover: string; partners_total: number; partners_active: number; bookings_total: number; revenue_total: string };
  customers: Array<{ id: number; name: string; email: string; phone: string; city_name: string; avatar_url: string; created_at: string; visits: number; last_visit: string | null; total_amount: string }>;
  partners: Array<{ id: number; name: string; contact_name: string; email: string; phone: string; category: string; is_active: boolean; created_at: string }>;
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

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "-" : new Intl.DateTimeFormat("ru-RU", { day: "2-digit", month: "2-digit", year: "numeric" }).format(date);
}

export default function AdminDashboardPage() {
  return <Suspense fallback={<main className={partnerStyles.screen}><section className={partnerStyles.contentArea}><div className={styles.content}><div className={styles.state}>Загружаем данные панели...</div></div></section></main>}><AdminDashboardContent /></Suspense>;
}

function AdminDashboardContent() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const requestedTab = searchParams.get("tab");
  const activeTab = requestedTab && navigation.some((item) => item.id === requestedTab) ? requestedTab : "dashboard";

  function setActiveTab(tab: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (tab === "dashboard") params.delete("tab");
    else params.set("tab", tab);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

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
        <div className={partnerStyles.headerMain}><h1 className={partnerStyles.headerTitle}>{tabLabel}</h1><p className={partnerStyles.headerSubtitle}>Админ</p></div>
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

function UsersTable({ customers }: { customers: DashboardData["customers"] }) {
  return <section className={styles.usersPage}>
    <div className={styles.usersHeading}><h2>Пользователи</h2><p>Управление пользователями, их подписками и статусами</p></div>
    {customers.length ? <div className={styles.usersTable}><div className={styles.usersTableHeader}><span>Пользователь</span><span>Контакты</span><span>Статус подписки</span><span>Дата регистрации</span><span>Дата окончания</span><span>Визиты</span><span>Сумма</span></div>{customers.map((customer) => <div className={styles.usersTableRow} key={customer.id}><span className={styles.userIdentity}>{customer.avatar_url ? <img src={customer.avatar_url} alt="" className={styles.userAvatar} /> : <i className={styles.userAvatar}>{customer.name.slice(0, 1).toUpperCase()}</i>}<span><b>{customer.name}</b><small>{customer.email || "Email не указан"}</small></span></span><span>{customer.phone}</span><span className={styles.subscriptionNone}>Отсутствует</span><span>{formatDate(customer.created_at)}</span><span>-</span><span>{customer.visits}</span><span>{formatMoney(customer.total_amount)}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}
  </section>;
}

function CustomersTable({ customers, onOpenUsers }: { customers: DashboardData["customers"]; onOpenUsers: () => void }) {
  return <section className={styles.customersSection}>
    <h2>Пользователи</h2>
    {customers.length ? <div className={styles.customerTable}><div className={styles.customerTableHeader}><span>ФИО пользователей</span><span>Телефон</span><span>Подписка</span><span>Последний визит</span><span>Визиты</span><span>Сумма</span></div>{customers.map((customer) => <div className={styles.customerTableRow} key={customer.id}><span className={styles.customerIdentity}>{customer.avatar_url ? <img src={customer.avatar_url} alt="" className={styles.customerAvatar} /> : <i className={styles.customerAvatar}>{customer.name.slice(0, 1).toUpperCase()}</i>}<span><b>{customer.name}</b><small>{customer.email || "Email не указан"}</small></span></span><span>{customer.phone}</span><span className={styles.noSubscription}>Нет</span><span>{formatDateTime(customer.last_visit)}</span><span>{customer.visits}</span><span>{formatMoney(customer.total_amount)}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}
    <button className={styles.allUsersButton} onClick={onOpenUsers}>Все пользователи</button>
  </section>;
}

function PartnersTable({ partners }: { partners: DashboardData["partners"] }) {
  const [items, setItems] = useState(partners);
  const [selectedPartner, setSelectedPartner] = useState<DashboardData["partners"][number] | null>(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<{ kind: "blocked" | "unblocked" | "error"; message: string } | null>(null);

  async function updateStatus() {
    if (!selectedPartner) return;
    const nextActive = !selectedPartner.is_active;
    setPending(true);
    try {
      const response = await fetch(`/api/admin/partners/${selectedPartner.id}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_active: nextActive }) });
      const payload = (await response.json()) as { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось обновить статус партнёра");
      setItems((current) => current.map((partner) => partner.id === selectedPartner.id ? { ...partner, is_active: nextActive } : partner));
      setNotice({ kind: nextActive ? "unblocked" : "blocked", message: selectedPartner.name });
      setSelectedPartner(null);
    } catch (error) {
      setNotice({ kind: "error", message: error instanceof Error ? error.message : "Не удалось обновить статус" });
    } finally {
      setPending(false);
    }
  }

  const blocking = selectedPartner?.is_active;
  return <section className={styles.partnersPage}>
    <div className={styles.partnersHeading}><h2>Управление партнёрами</h2><p>Управление пользователями, их подписками и статусами</p></div>
    {items.length ? <div className={styles.partnersTable}><div className={styles.partnersTableHeader}><span>Компания</span><span>Контакты</span><span>Категория</span><span>Статус</span><span>Дата регистрации</span><span>Действия</span></div>{items.map((partner) => <div className={styles.partnersTableRow} key={partner.id}><span><b>{partner.name}</b><small>юр.лицо</small></span><span><b>{partner.contact_name || partner.email || "Контакт не указан"}</b><small>{partner.phone || "Телефон не указан"}</small></span><span>{partner.category || "Не указана"}</span><span className={partner.is_active ? styles.partnerActive : styles.partnerBlocked}>{partner.is_active ? "Активен" : "Заблокирован"}</span><span>{formatDate(partner.created_at)}</span><span className={styles.partnerActions}><Eye size={15} strokeWidth={1.8} aria-hidden="true" /><button className={styles.lockButton} onClick={() => setSelectedPartner(partner)} aria-label={partner.is_active ? `Заблокировать ${partner.name}` : `Разблокировать ${partner.name}`} title={partner.is_active ? "Заблокировать" : "Разблокировать"}>{partner.is_active ? <LockKeyhole size={15} strokeWidth={1.8} /> : <UnlockKeyhole size={15} strokeWidth={1.8} />}</button></span></div>)}</div> : <div className={styles.empty}>Партнёров пока нет.</div>}
    {notice ? <div className={`${styles.partnerNotice} ${notice.kind === "unblocked" ? styles.partnerNoticeInfo : styles.partnerNoticeBlocked}`} role="status"><b>{notice.kind === "unblocked" ? "Партнёр разблокирован" : notice.kind === "blocked" ? "Партнёр заблокирован" : "Ошибка"}</b><span>{notice.message}</span><button onClick={() => setNotice(null)} aria-label="Закрыть уведомление">×</button></div> : null}
    {selectedPartner ? <div className={styles.modalBackdrop} role="presentation"><section className={styles.statusModal} role="dialog" aria-modal="true" aria-labelledby="partner-status-title"><div className={`${styles.statusIcon} ${blocking ? styles.statusIconBlock : styles.statusIconUnblock}`}>{blocking ? "🔒" : "🔓"}</div><h2 id="partner-status-title">{blocking ? "Заблокировать партнёра" : "Разблокировать партнёра"}</h2><p>Вы уверены, что хотите {blocking ? "заблокировать" : "разблокировать"} партнёра?</p><div><button disabled={pending} onClick={() => setSelectedPartner(null)}>Отменить</button><button className={blocking ? styles.blockConfirm : styles.unblockConfirm} disabled={pending} onClick={() => void updateStatus()}>{pending ? "Сохраняем..." : blocking ? "Заблокировать" : "Разблокировать"}</button></div></section></div> : null}
  </section>;
}