"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useRef, useState } from "react";
import { Archive, ArrowLeft, CalendarDays, Car, Clock3, Coffee, Crown, Droplets, Dumbbell, Eye, GraduationCap, HeartPulse, LockKeyhole, Mountain, Pause, Pencil, Plus, RotateCcw, Sparkles, Store, UnlockKeyhole, X } from "lucide-react";
import { formatRuPhone } from "../../../lib/phone";
import partnerStyles from "../../partner/dashboard/layout.module.css";
import styles from "./page.module.css";

type DashboardData = {
  admin: { name: string; email: string };
  metrics: { customers_total: number; subscriptions_active: number; customers_without_subscription: number; customers_turnover: string; partners_total: number; partners_active: number; bookings_total: number; revenue_total: string };
  customers: Array<{ id: number; name: string; email: string; phone: string; city_name: string; avatar_url: string; created_at: string; visits: number; last_visit: string | null; total_amount: string; subscription: CustomerSubscription | null; subscription_active: boolean }>;
  partners: Array<{ id: number; name: string; contact_name: string; email: string; phone: string; category: string; is_active: boolean; created_at: string }>;
};

type CustomerSubscription = { id: number; plan_name: string; status: "active" | "paused"; expires_at: string | null };

type SubscriptionPlan = { id: number; name: string; monthly_price: number; duration_months: number; description: string; is_archived: boolean };
type BusinessCategory = { id: number; name: string; is_archived: boolean; allows_group_services: boolean };
type SubscriptionCatalog = { plans: SubscriptionPlan[]; categories: BusinessCategory[] };

type CustomerDetail = {
  customer: { id: number; name: string; email: string; phone: string; city_name: string; avatar_url: string | null; created_at: string; is_active: boolean };
  subscription: CustomerSubscription | null;
  visits: Array<{ id: number; starts_at: string; company: string; service_name: string; final_price: string; status: string }>;
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
  const requestedUserId = searchParams.get("user");
  const userId = activeTab === "users" && requestedUserId && /^\d+$/.test(requestedUserId) ? Number(requestedUserId) : null;

  function setActiveTab(tab: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.delete("user");
    if (tab === "dashboard") params.delete("tab");
    else params.set("tab", tab);
    const query = params.toString();
    router.push(query ? `${pathname}?${query}` : pathname);
  }

  function openUserProfile(customerId: number) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", "users");
    params.set("user", customerId.toString());
    router.push(`${pathname}?${params.toString()}`);
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
        <div className={partnerStyles.headerMain}><h1 className={partnerStyles.headerTitle}>{activeTab === "subscriptions" ? "Подписки и категории" : tabLabel}</h1><p className={partnerStyles.headerSubtitle}>Админ</p></div>
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
          {!loading && !error && data ? <TabContent activeTab={activeTab} data={data} userId={userId} onOpenUsers={() => setActiveTab("users")} onOpenUserProfile={openUserProfile} onCloseUserProfile={() => setActiveTab("users")} /> : null}
        </div>
      </section>
    </main>
  );
}

function TabContent({ activeTab, data, userId, onOpenUsers, onOpenUserProfile, onCloseUserProfile }: { activeTab: string; data: DashboardData; userId: number | null; onOpenUsers: () => void; onOpenUserProfile: (customerId: number) => void; onCloseUserProfile: () => void }) {
  if (activeTab === "users") return userId ? <CustomerProfile customerId={userId} onBack={onCloseUserProfile} /> : <UsersTable customers={data.customers} onOpenProfile={onOpenUserProfile} />;
  if (activeTab === "partners") return <PartnersTable partners={data.partners} />;
  if (activeTab === "subscriptions") return <SubscriptionsPage />;
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

function SubscriptionStatus({ customer }: { customer: DashboardData["customers"][number] }) {
  const label = customer.subscription_active ? "Активна" : customer.subscription?.status === "paused" ? "Приостановлена" : customer.subscription ? "Истекла" : "Отсутствует";
  return <span className={customer.subscription_active ? styles.subscriptionActive : styles.subscriptionNone}>{label}</span>;
}

function UsersTable({ customers, onOpenProfile }: { customers: DashboardData["customers"]; onOpenProfile: (customerId: number) => void }) {
  return <section className={styles.usersPage}>
    <div className={styles.usersHeading}><h2>Пользователи</h2><p>Управление пользователями, их подписками и статусами</p></div>
    {customers.length ? <div className={styles.usersTable}><div className={styles.usersTableHeader}><span>Пользователь</span><span>Контакты</span><span>Статус подписки</span><span>Дата регистрации</span><span>Дата окончания</span><span>Визиты</span><span>Сумма</span></div>{customers.map((customer) => <div className={`${styles.usersTableRow} ${styles.userProfileRow}`} key={customer.id} role="button" tabIndex={0} onClick={() => onOpenProfile(customer.id)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") onOpenProfile(customer.id); }}><span className={styles.userIdentity}>{customer.avatar_url ? <img src={customer.avatar_url} alt="" className={styles.userAvatar} /> : <i className={styles.userAvatar}>{customer.name.slice(0, 1).toUpperCase()}</i>}<span><b>{customer.name}</b><small>{customer.email || "Email не указан"}</small></span></span><span>{formatRuPhone(customer.phone)}</span><SubscriptionStatus customer={customer} /><span>{formatDate(customer.created_at)}</span><span>{customer.subscription?.expires_at ? formatDate(customer.subscription.expires_at) : "-"}</span><span>{customer.visits}</span><span>{formatMoney(customer.total_amount)}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}
  </section>;
}

function CustomerProfile({ customerId, onBack }: { customerId: number; onBack: () => void }) {
  const [profile, setProfile] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<"pause" | "extend" | null>(null);
  const [extensionDate, setExtensionDate] = useState("");
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    async function loadProfile() {
      setLoading(true);
      setError("");
      try {
        const response = await fetch(`/api/admin/customers/${customerId}`, { cache: "no-store", signal: controller.signal });
        const payload = (await response.json()) as CustomerDetail & { message?: string };
        if (!response.ok) throw new Error(payload.message || "Не удалось загрузить профиль пользователя");
        setProfile(payload);
      } catch (loadError) {
        if (!controller.signal.aborted) setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить профиль пользователя");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void loadProfile();
    return () => controller.abort();
  }, [customerId]);

  if (loading) return <div className={styles.state}>Загружаем профиль пользователя...</div>;
  if (error || !profile) return <div className={styles.state}><p>{error || "Профиль пользователя не найден"}</p><button onClick={onBack}>Вернуться к пользователям</button></div>;

  const subscription = profile.subscription;
  const isSubscriptionActive = subscription?.status === "active";

  function openDialog(nextDialog: "pause" | "extend") {
    if (!subscription) return;
    setActionError("");
    setExtensionDate(nextDialog === "extend" ? subscription.expires_at || "" : "");
    setDialog(nextDialog);
  }

  async function saveSubscriptionAction() {
    if (!dialog || !subscription) return;
    setSaving(true);
    setActionError("");
    try {
      const body = dialog === "pause" ? { action: "pause" } : { action: "extend", expires_at: extensionDate };
      const response = await fetch(`/api/admin/customers/${customerId}/subscription`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const payload = (await response.json()) as { subscription?: CustomerSubscription; message?: string };
      if (!response.ok || !payload.subscription) throw new Error(payload.message || "Не удалось обновить подписку");
      setProfile((current) => current ? { ...current, subscription: payload.subscription || current.subscription } : current);
      setDialog(null);
    } catch (saveError) {
      setActionError(saveError instanceof Error ? saveError.message : "Не удалось обновить подписку");
    } finally {
      setSaving(false);
    }
  }

  return <section className={styles.customerProfilePage}>
    <button className={styles.profileBack} onClick={onBack}><ArrowLeft size={18} strokeWidth={1.8} /> Профиль пользователя</button>
    <div className={styles.profileSummary}>
      <article className={styles.profileCard}>
        <div className={styles.profileCardHead}><h2>Основные данные</h2><span className={profile.customer.is_active ? styles.accountActive : styles.accountBlocked}>{profile.customer.is_active ? "Аккаунт активен" : "Аккаунт заблокирован"}</span></div>
        <div className={styles.profileIdentity}>{profile.customer.avatar_url ? <img src={profile.customer.avatar_url} alt="" className={styles.profileAvatar} /> : <i className={styles.profileAvatar}>{profile.customer.name.slice(0, 1).toUpperCase()}</i>}<strong>{profile.customer.name}</strong><small>Регистрация: {formatDate(profile.customer.created_at)}</small></div>
        <dl className={styles.profileContacts}><div><dt>Телефон</dt><dd>{formatRuPhone(profile.customer.phone)}</dd></div><div><dt>Email</dt><dd>{profile.customer.email || "Не указан"}</dd></div></dl>
      </article>
      <article className={styles.subscriptionCard}>
        <h2>Статус подписки</h2>
        <div className={styles.subscriptionCurrent}><p>Текущая подписка</p><strong>{subscription?.plan_name || "Отсутствует"}</strong>{subscription ? <span className={isSubscriptionActive ? styles.subscriptionActive : styles.subscriptionPaused}>{isSubscriptionActive ? "Активна" : "Приостановлена"}</span> : null}</div>
        <div className={styles.subscriptionExpiry}><span>Срок действия до</span><strong>{subscription?.expires_at ? formatDate(subscription.expires_at) : "—"}</strong></div>
        <div className={styles.subscriptionActions}><button disabled={!isSubscriptionActive} title={subscription ? "Приостановить подписку" : "У пользователя нет подписки"} onClick={() => openDialog("pause")}>Приостановить</button><button disabled={!subscription} title={subscription ? "Продлить подписку" : "У пользователя нет подписки"} onClick={() => openDialog("extend")}>Продлить подписку</button></div>
      </article>
    </div>
    <section className={styles.visitHistory}><h2>История визитов</h2>{profile.visits.length ? <div className={styles.historyTable}><div className={styles.historyTableHead}><span>Дата и время</span><span>Компания</span><span>Услуги</span><span>Итоговая стоимость</span></div>{profile.visits.map((visit) => <div className={styles.historyTableRow} key={visit.id}><span><b>{formatDate(visit.starts_at)}</b><small>{new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(new Date(visit.starts_at))}</small></span><span>{visit.company}</span><span>{visit.service_name}</span><span>{Number(visit.final_price) > 0 ? formatMoney(visit.final_price) : "—"}</span></div>)}</div> : <div className={styles.profileEmpty}>Визитов пока нет.</div>}</section>
    {dialog ? <div className={styles.subscriptionModalBackdrop} role="presentation"><section className={styles.subscriptionModal} role="dialog" aria-modal="true" aria-labelledby="subscription-dialog-title"><div className={styles.subscriptionModalIcon}>{dialog === "pause" ? <Pause size={31} strokeWidth={1.8} /> : <CalendarDays size={29} strokeWidth={1.8} />}</div><h2 id="subscription-dialog-title">{dialog === "pause" ? "Приостановить подписку" : "Продлить подписку"}</h2>{dialog === "pause" ? <p>Вы точно хотите приостановить подписку пользователя<br />«{profile.customer.name}»?</p> : <p>До какого числа вы хотите продлить подписку?</p>}{dialog === "extend" ? <label className={styles.subscriptionDateInput}><CalendarDays size={16} strokeWidth={1.8} /><input type="date" value={extensionDate} min={new Date().toISOString().slice(0, 10)} onChange={(event) => setExtensionDate(event.target.value)} /></label> : null}{actionError ? <p className={styles.subscriptionActionError}>{actionError}</p> : null}<div className={styles.subscriptionModalActions}><button disabled={saving} onClick={() => setDialog(null)}>Отменить</button><button className={styles.subscriptionConfirm} disabled={saving || (dialog === "extend" && !extensionDate)} onClick={() => void saveSubscriptionAction()}>{saving ? "Сохраняем..." : dialog === "pause" ? "Да, приостановить" : "Сохранить"}</button></div></section></div> : null}
  </section>;
}

function CustomersTable({ customers, onOpenUsers }: { customers: DashboardData["customers"]; onOpenUsers: () => void }) {
  return <section className={styles.customersSection}>
    <h2>Пользователи</h2>
    {customers.length ? <div className={styles.customerTable}><div className={styles.customerTableHeader}><span>ФИО пользователей</span><span>Телефон</span><span>Подписка</span><span>Последний визит</span><span>Визиты</span><span>Сумма</span></div>{customers.map((customer) => <div className={styles.customerTableRow} key={customer.id}><span className={styles.customerIdentity}>{customer.avatar_url ? <img src={customer.avatar_url} alt="" className={styles.customerAvatar} /> : <i className={styles.customerAvatar}>{customer.name.slice(0, 1).toUpperCase()}</i>}<span><b>{customer.name}</b><small>{customer.email || "Email не указан"}</small></span></span><span>{formatRuPhone(customer.phone)}</span><SubscriptionStatus customer={customer} /><span>{formatDateTime(customer.last_visit)}</span><span>{customer.visits}</span><span>{formatMoney(customer.total_amount)}</span></div>)}</div> : <div className={styles.empty}>Пользователей пока нет.</div>}
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
    {items.length ? <div className={styles.partnersTable}><div className={styles.partnersTableHeader}><span>Компания</span><span>Контакты</span><span>Категория</span><span>Статус</span><span>Дата регистрации</span><span>Действия</span></div>{items.map((partner) => <div className={styles.partnersTableRow} key={partner.id}><span><b>{partner.name}</b></span><span><b>{partner.contact_name || partner.email || "Контакт не указан"}</b><small>{partner.phone ? formatRuPhone(partner.phone) : "Телефон не указан"}</small></span><span>{partner.category || "Не указана"}</span><span className={partner.is_active ? styles.partnerActive : styles.partnerBlocked}>{partner.is_active ? "Активен" : "Заблокирован"}</span><span>{formatDate(partner.created_at)}</span><span className={styles.partnerActions}><Eye size={15} strokeWidth={1.8} aria-hidden="true" /><button className={styles.lockButton} onClick={() => setSelectedPartner(partner)} aria-label={partner.is_active ? `Заблокировать ${partner.name}` : `Разблокировать ${partner.name}`} title={partner.is_active ? "Заблокировать" : "Разблокировать"}>{partner.is_active ? <LockKeyhole size={15} strokeWidth={1.8} /> : <UnlockKeyhole size={15} strokeWidth={1.8} />}</button></span></div>)}</div> : <div className={styles.empty}>Партнёров пока нет.</div>}
    {notice ? <div className={`${styles.partnerNotice} ${notice.kind === "unblocked" ? styles.partnerNoticeInfo : styles.partnerNoticeBlocked}`} role="status"><b>{notice.kind === "unblocked" ? "Партнёр разблокирован" : notice.kind === "blocked" ? "Партнёр заблокирован" : "Ошибка"}</b><span>{notice.message}</span><button onClick={() => setNotice(null)} aria-label="Закрыть уведомление">×</button></div> : null}
    {selectedPartner ? <div className={styles.modalBackdrop} role="presentation"><section className={styles.statusModal} role="dialog" aria-modal="true" aria-labelledby="partner-status-title"><div className={`${styles.statusIcon} ${blocking ? styles.statusIconBlock : styles.statusIconUnblock}`}>{blocking ? "🔒" : "🔓"}</div><h2 id="partner-status-title">{blocking ? "Заблокировать партнёра" : "Разблокировать партнёра"}</h2><p>Вы уверены, что хотите {blocking ? "заблокировать" : "разблокировать"} партнёра?</p><div><button disabled={pending} onClick={() => setSelectedPartner(null)}>Отменить</button><button className={blocking ? styles.blockConfirm : styles.unblockConfirm} disabled={pending} onClick={() => void updateStatus()}>{pending ? "Сохраняем..." : blocking ? "Заблокировать" : "Разблокировать"}</button></div></section></div> : null}
  </section>;
}

function SubscriptionsPage() {
  const [catalog, setCatalog] = useState<SubscriptionCatalog | null>(null);
  const [filter, setFilter] = useState<"active" | "archived" | "all">("all");
  const [dialog, setDialog] = useState<{ resource: "plans" | "categories"; item?: SubscriptionPlan | BusinessCategory } | null>(null);
  const [archiveTarget, setArchiveTarget] = useState<{ resource: "plans" | "categories"; item: SubscriptionPlan | BusinessCategory } | null>(null);
  const [notice, setNotice] = useState<{ restored: boolean; title: string; name: string } | null>(null);
  const [actionError, setActionError] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  function openEditor(resource: "plans" | "categories", item?: SubscriptionPlan | BusinessCategory) {
    setActionError("");
    setDialog({ resource, item });
  }

  function openArchive(resource: "plans" | "categories", item: SubscriptionPlan | BusinessCategory) {
    setActionError("");
    setArchiveTarget({ resource, item });
  }

  async function loadCatalog() {
    setError("");
    try {
      const response = await fetch("/api/admin/subscriptions", { cache: "no-store" });
      const payload = (await response.json()) as SubscriptionCatalog & { message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось загрузить подписки");
      setCatalog(payload);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Не удалось загрузить подписки");
    }
  }

  useEffect(() => { void loadCatalog(); }, []);

  async function saveItem(values: { name: string; monthly_price?: number; duration_months?: number; description?: string; allows_group_services?: boolean }) {
    if (!dialog) return;
    setSaving(true);
    setActionError("");
    try {
      const isPlan = dialog.resource === "plans";
      const response = dialog.item
        ? await fetch(`/api/admin/subscriptions/${dialog.resource}/${dialog.item.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(values) })
        : await fetch("/api/admin/subscriptions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ resource: dialog.resource, ...values }) });
      const payload = (await response.json()) as { plan?: SubscriptionPlan; category?: BusinessCategory; message?: string };
      if (!response.ok) throw new Error(payload.message || "Не удалось сохранить изменения");
      const item = isPlan ? payload.plan : payload.category;
      if (!item) throw new Error("Сервер вернул неполные данные");
      setCatalog((current) => {
        if (!current) return current;
        const key = isPlan ? "plans" : "categories";
        const currentItems = current[key] as Array<SubscriptionPlan | BusinessCategory>;
        const nextItems = dialog.item ? currentItems.map((currentItem) => currentItem.id === item.id ? item : currentItem) : [...currentItems, item];
        return { ...current, [key]: nextItems } as SubscriptionCatalog;
      });
      setDialog(null);
    } catch (saveError) {
      setActionError(saveError instanceof Error ? saveError.message : "Не удалось сохранить изменения");
    } finally {
      setSaving(false);
    }
  }

  async function confirmArchive() {
    if (!archiveTarget) return;
    const { resource, item } = archiveTarget;
    setSaving(true);
    setActionError("");
    try {
      const response = await fetch(`/api/admin/subscriptions/${resource}/${item.id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ is_archived: !item.is_archived }) });
      const payload = (await response.json()) as { plan?: SubscriptionPlan; category?: BusinessCategory; message?: string };
      const updated = resource === "plans" ? payload.plan : payload.category;
      if (!response.ok || !updated) throw new Error(payload.message || "Не удалось обновить статус");
      setCatalog((current) => current ? { ...current, [resource]: current[resource].map((currentItem) => currentItem.id === updated.id ? updated : currentItem) } as SubscriptionCatalog : current);
      setNotice({ restored: item.is_archived, title: resource === "plans" ? (item.is_archived ? "Подписка восстановлена" : "Подписка архивирована") : (item.is_archived ? "Категория восстановлена" : "Категория архивирована"), name: item.name });
      setArchiveTarget(null);
    } catch (archiveError) {
      setActionError(archiveError instanceof Error ? archiveError.message : "Не удалось обновить статус");
    } finally {
      setSaving(false);
    }
  }

  if (!catalog && !error) return <div className={styles.state}>Загружаем подписки...</div>;
  if (!catalog) return <div className={styles.state}><p>{error}</p><button onClick={() => void loadCatalog()}>Повторить</button></div>;

  const isVisible = (item: { is_archived: boolean }) => filter === "all" || (filter === "archived" ? item.is_archived : !item.is_archived);
  const plans = catalog.plans.filter(isVisible);
  const categories = catalog.categories;
  const activeCount = catalog.plans.filter((item) => !item.is_archived).length;
  const archivedCount = catalog.plans.filter((item) => item.is_archived).length;

  return <section className={styles.subscriptionsPage}>
    <div className={styles.subscriptionsToolbar}><p>Управление подписками и категориями партнёров</p><div className={styles.subscriptionFilters}><button className={filter === "active" ? styles.subscriptionFilterActive : ""} onClick={() => setFilter("active")}>Активные ({activeCount})</button><button className={filter === "archived" ? styles.subscriptionFilterActive : ""} onClick={() => setFilter("archived")}>Архивные ({archivedCount})</button><button className={filter === "all" ? styles.subscriptionFilterActive : ""} onClick={() => setFilter("all")}>Все</button></div></div>
    {error ? <p className={styles.catalogError}>{error}</p> : null}
    <div className={styles.subscriptionGrid}>
      <section className={styles.plansColumn}>
        <div className={styles.catalogHeading}><h2>Тарифные планы</h2><button onClick={() => openEditor("plans")}><Plus size={15} /> Добавить тариф</button></div>
        {plans.length ? <div className={styles.planList}>{plans.map((plan) => <article className={styles.planCard} key={plan.id}>
          <div className={styles.planCardHead}><h3>{plan.name} <span className={plan.is_archived ? "" : styles.planActiveBadge}>{plan.is_archived ? "Архивный" : "Активен"}</span></h3><strong>{formatMoney(plan.monthly_price.toString())}<small>/ мес.</small></strong></div>
          <p className={styles.planDuration}><Clock3 size={13} /> Срок действия: <b>{plan.duration_months} мес.</b></p>
          <p className={styles.planDescription}>{plan.description || "Описание не указано"}</p>
          <div className={styles.planActions}><button onClick={() => openEditor("plans", plan)}><Pencil size={14} /> Изменить</button><button className={styles.catalogIconButton} onClick={() => openArchive("plans", plan)} aria-label={plan.is_archived ? `Восстановить подписку ${plan.name}` : `Архивировать подписку ${plan.name}`} title={plan.is_archived ? "Восстановить" : "Архивировать"}>{plan.is_archived ? <RotateCcw size={15} /> : <Archive size={15} />}</button></div>
        </article>)}</div> : <div className={styles.catalogEmpty}>Подписок в этом разделе нет.</div>}
      </section>
      <section className={styles.categoriesColumn}>
        <div className={styles.catalogHeading}><h2>Категории</h2><button onClick={() => openEditor("categories")}><Plus size={15} /> Добавить категорию</button></div>
        <div className={styles.categoryList}>{categories.length ? categories.map((category) => <article className={styles.categoryItem} key={category.id}>
          <span className={styles.categoryMark}><CategoryIcon name={category.name} /></span><b title={category.name}>{category.name}</b><small className={category.is_archived ? styles.categoryArchived : ""}>{category.is_archived ? "Архивная" : "Активна"}</small>
          <button onClick={() => openEditor("categories", category)} aria-label={`Изменить категорию ${category.name}`} title="Изменить"><Pencil size={15} /></button><button onClick={() => openArchive("categories", category)} aria-label={category.is_archived ? `Восстановить категорию ${category.name}` : `Архивировать категорию ${category.name}`} title={category.is_archived ? "Восстановить" : "Архивировать"}>{category.is_archived ? <RotateCcw size={15} /> : <Archive size={15} />}</button>
        </article>) : <div className={styles.catalogEmpty}>Категорий пока нет.</div>}</div>
      </section>
    </div>
    {notice ? <div className={`${styles.partnerNotice} ${styles.catalogNotice} ${notice.restored ? styles.partnerNoticeInfo : styles.partnerNoticeBlocked}`} role="status"><b>{notice.title}</b><span>{notice.name}</span><button onClick={() => setNotice(null)} aria-label="Закрыть уведомление"><X size={20} /></button></div> : null}
    {dialog ? <CatalogDialog dialog={dialog} saving={saving} error={actionError} onClose={() => { if (!saving) setDialog(null); }} onSave={saveItem} /> : null}
    {archiveTarget ? <CatalogArchiveDialog target={archiveTarget} saving={saving} error={actionError} onClose={() => { if (!saving) setArchiveTarget(null); }} onConfirm={() => void confirmArchive()} /> : null}
  </section>;
}

function CategoryIcon({ name }: { name: string }) {
  const Icon = /авто/i.test(name) ? Car : /кафе|ресторан/i.test(name) ? Coffee : /медицин/i.test(name) ? HeartPulse : /спорт/i.test(name) ? Dumbbell : /кружк|курс/i.test(name) ? GraduationCap : /красот/i.test(name) ? Sparkles : /мойк/i.test(name) ? Droplets : /туризм|отдых/i.test(name) ? Mountain : Store;
  return <Icon size={14} strokeWidth={1.8} aria-hidden="true" />;
}

function useDialogDrag(onClose: () => void) {
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; offsetX: number; offsetY: number; minX: number; maxX: number; minY: number; maxY: number } | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  useEffect(() => {
    function escape(event: KeyboardEvent) { if (event.key === "Escape") closeRef.current(); }
    window.addEventListener("keydown", escape);
    return () => window.removeEventListener("keydown", escape);
  }, []);

  const dragHandlers = {
    onPointerDown(event: React.PointerEvent<HTMLElement>) {
      if (event.button !== 0 || (event.target as HTMLElement).closest("button")) return;
      const dialogElement = event.currentTarget.closest('[role="dialog"]');
      if (!dialogElement) return;
      const rect = dialogElement.getBoundingClientRect();
      drag.current = { x: event.clientX, y: event.clientY, offsetX: offset.x, offsetY: offset.y, minX: offset.x + 8 - rect.left, maxX: offset.x + window.innerWidth - 8 - rect.right, minY: offset.y + 8 - rect.top, maxY: offset.y + window.innerHeight - 8 - rect.bottom };
      event.currentTarget.setPointerCapture(event.pointerId);
      event.preventDefault();
    },
    onPointerMove(event: React.PointerEvent<HTMLElement>) {
      const start = drag.current;
      if (!start) return;
      setOffset({ x: Math.min(Math.max(start.offsetX + event.clientX - start.x, start.minX), start.maxX), y: Math.min(Math.max(start.offsetY + event.clientY - start.y, start.minY), start.maxY) });
    },
    onPointerUp() { drag.current = null; },
    onPointerCancel() { drag.current = null; },
    onLostPointerCapture() { drag.current = null; },
  };
  return { dragHandlers, positionStyle: { transform: `translate(${offset.x}px, ${offset.y}px)` } };
}

function CatalogArchiveDialog({ target, saving, error, onClose, onConfirm }: { target: { resource: "plans" | "categories"; item: SubscriptionPlan | BusinessCategory }; saving: boolean; error: string; onClose: () => void; onConfirm: () => void }) {
  const { dragHandlers, positionStyle } = useDialogDrag(onClose);
  const restoring = target.item.is_archived;
  const objectName = target.resource === "plans" ? "подписку" : "категорию";
  const action = restoring ? "Восстановить" : "Архивировать";
  return <div className={styles.modalBackdrop} role="presentation"><section className={`${styles.statusModal} ${styles.catalogArchiveModal}`} style={positionStyle} role="dialog" aria-modal="true" aria-labelledby="catalog-archive-title">
    <header className={styles.catalogDragHandle} {...dragHandlers}><div className={`${styles.statusIcon} ${styles.statusIconBlock}`}>{restoring ? <RotateCcw size={30} /> : <Archive size={30} />}</div><h2 id="catalog-archive-title">{action} {objectName}</h2></header>
    <p>Вы уверены, что хотите {action.toLowerCase()} {objectName} «{target.item.name}»?</p>
    {error ? <p className={styles.catalogError} role="alert">{error}</p> : null}
    <div><button autoFocus disabled={saving} onClick={onClose}>Отменить</button><button className={restoring ? styles.unblockConfirm : styles.blockConfirm} disabled={saving} onClick={onConfirm}>{saving ? "Сохраняем..." : action}</button></div>
  </section></div>;
}

function CatalogDialog({ dialog, saving, error, onClose, onSave }: { dialog: { resource: "plans" | "categories"; item?: SubscriptionPlan | BusinessCategory }; saving: boolean; error: string; onClose: () => void; onSave: (values: { name: string; monthly_price?: number; duration_months?: number; description?: string; allows_group_services?: boolean }) => void }) {
  const { dragHandlers, positionStyle } = useDialogDrag(onClose);
  const plan = dialog.resource === "plans" ? dialog.item as SubscriptionPlan | undefined : undefined;
  const [name, setName] = useState(dialog.item?.name || "");
  const [price, setPrice] = useState(plan?.monthly_price.toString() || "");
  const [duration, setDuration] = useState(plan?.duration_months.toString() || "12");
  const [description, setDescription] = useState(plan?.description || "");
  const [allowsGroups, setAllowsGroups] = useState(dialog.resource === "categories" ? (dialog.item as BusinessCategory | undefined)?.allows_group_services || false : false);
  const isPlan = dialog.resource === "plans";
  function submit(event: React.FormEvent<HTMLFormElement>) { event.preventDefault(); onSave(isPlan ? { name, monthly_price: Number(price), duration_months: Number(duration), description } : { name, allows_group_services: allowsGroups }); }
  const title = `${dialog.item ? "Изменить" : "Добавить"} ${isPlan ? "подписку" : "категорию"}`;
  return <div className={styles.catalogModalBackdrop}><form className={styles.catalogModal} style={positionStyle} onSubmit={submit} role="dialog" aria-modal="true" aria-labelledby="catalog-editor-title">
    <header className={styles.catalogDragHandle} {...dragHandlers}><Crown size={20} className={styles.catalogCrown} /><b id="catalog-editor-title">{title}</b><button type="button" disabled={saving} onClick={onClose} aria-label="Закрыть"><X size={18} /></button></header>
    <label>Название {isPlan ? "подписки" : "категории"}<input autoFocus value={name} disabled={saving} onChange={(event) => setName(event.target.value)} required maxLength={120} /></label>
    {!isPlan ? <label className={styles.catalogGroupToggle}><span>Групповые занятия</span><input type="checkbox" role="switch" checked={allowsGroups} disabled={saving} onChange={(event) => setAllowsGroups(event.target.checked)} /></label> : null}
    {isPlan ? <><label>Стоимость (₸ / мес)<input type="number" value={price} disabled={saving} onChange={(event) => setPrice(event.target.value)} min="0" step="1" required /></label><label>Срок действия (мес)<input type="number" value={duration} disabled={saving} onChange={(event) => setDuration(event.target.value)} min="1" max="32767" step="1" required /></label><label>Описание<textarea value={description} disabled={saving} onChange={(event) => setDescription(event.target.value)} rows={4} /></label></> : null}
    {error ? <p className={styles.catalogDialogError} role="alert">{error}</p> : null}
    <footer><button type="button" disabled={saving} onClick={onClose}>Отменить</button><button className={styles.catalogSubmit} disabled={saving}>{saving ? "Сохраняем..." : dialog.item ? "Сохранить" : "Создать"}</button></footer>
  </form></div>;
}