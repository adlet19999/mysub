"use client";

import Link from "next/link";
import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, CalendarDays, Check, ChevronDown, Clock3, Plus, Search, Users, X } from "lucide-react";
import { BookingGroup, enrollmentTotal, GroupDetail, GroupParticipant, GroupSession, isActiveVisit, lessonCount, selectableSessions } from "../../../../lib/groups";
import { formatRuPhone } from "../../../../lib/phone";
import AvailableTimeSelect from "../schedule/AvailableTimeSelect";
import PassVisitEditor, { PassVisit } from "../schedule/PassVisitEditor";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
type Service = { id: number; name: string; service_type: string; is_active: boolean; is_pass: boolean; visit_count: number; price: string | null; pass_price_mode: "total" | "per_visit"; details: { max_people?: number } };
type Specialist = { id: number; full_name: string; is_active: boolean; service_ids: number[] };
type Modal = { kind: "create" } | { kind: "enroll" } | { kind: "move"; booking: GroupParticipant } | { kind: "cancel"; booking: GroupParticipant } | { kind: "lesson-move"; session: GroupSession } | { kind: "lesson-cancel"; session: GroupSession };
const money = (value: number | string) => `${Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} ₸`;
const dateLabel = (value: string) => new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "short", timeZone: "Asia/Almaty" }).format(new Date(value));
const timeLabel = (value: string) => new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Almaty" }).format(new Date(value));
const dateInput = (value: Date) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
const complete = (status: string) => ["completed", "done", "завершен", "завершена"].includes(status);
const statusLabel = (status: string) => complete(status) ? "Посетил" : ["no_show", "no-show", "missed", "неявка"].includes(status) ? "Неявка" : isActiveVisit(status) ? "Записан" : "Отменено";

function Dialog({ title, busy, onClose, children }: { title: string; busy: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    dialog?.showModal();
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { dialog?.close(); document.body.style.overflow = previous; };
  }, []);
  return <dialog ref={ref} className={styles.dialog} aria-labelledby="group-dialog-title" onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }}>
    <header className={styles.dialogHeader}><h2 id="group-dialog-title">{title}</h2><button type="button" className={styles.iconButton} onClick={onClose} disabled={busy} aria-label="Закрыть"><X size={20} /></button></header>
    {children}
  </dialog>;
}

export default function GroupsPage() {
  const [email, setEmail] = useState("");
  const [groups, setGroups] = useState<BookingGroup[]>([]);
  const [sessions, setSessions] = useState<GroupSession[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [specialists, setSpecialists] = useState<Specialist[]>([]);
  const [detail, setDetail] = useState<GroupDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [formError, setFormError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [tab, setTab] = useState<"sessions" | "members">("sessions");
  const [expanded, setExpanded] = useState<number[]>([]);
  const [modal, setModal] = useState<Modal | null>(null);
  const [name, setName] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [specialistId, setSpecialistId] = useState("");
  const [capacity, setCapacity] = useState(1);
  const [count, setCount] = useState(1);
  const [firstDate, setFirstDate] = useState(() => dateInput(new Date()));
  const [firstTime, setFirstTime] = useState("");
  const [visits, setVisits] = useState<PassVisit[]>([]);
  const [clientName, setClientName] = useState("");
  const [phone, setPhone] = useState("");
  const [selectedSessions, setSelectedSessions] = useState<number[]>([]);
  const [moveMode, setMoveMode] = useState<"group" | "separate">("group");
  const [targetSession, setTargetSession] = useState("");
  const requestKey = useRef<{ payload: string; key: string } | null>(null);
  const loadSequence = useRef(0);

  const request = useCallback(async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
    const response = await fetch(`${API_BASE}/partner/${path}`, {
      ...init, cache: "no-store",
      headers: { "Content-Type": "application/json", "X-Partner-Email": email, "X-Tenant": TENANT },
    });
    const payload: T & { message?: string } = await response.json();
    if (!response.ok) throw new Error(payload.message || "Не удалось выполнить действие");
    return payload;
  }, [email]);

  const load = useCallback(async (groupId?: number) => {
    const sequence = ++loadSequence.current;
    setLoading(true);
    setError("");
    try {
      const [groupList, sessionList, serviceList, specialistList, group] = await Promise.all([
        request<{ items: BookingGroup[] }>("groups/"),
        request<{ items: GroupSession[] }>("groups/sessions/"),
        request<Service[]>("services/"), request<Specialist[]>("specialists/"),
        groupId ? request<GroupDetail>(`groups/${groupId}/`) : Promise.resolve(null),
      ]);
      if (sequence !== loadSequence.current) return;
      if (!Array.isArray(groupList.items) || !Array.isArray(sessionList.items) || !Array.isArray(serviceList) || !Array.isArray(specialistList)) throw new Error("Некорректный ответ сервера");
      setGroups(groupList.items); setSessions(sessionList.items); setServices(serviceList); setSpecialists(specialistList); setDetail(group);
      const params = new URLSearchParams(window.location.search);
      if (groupId) params.set("group", String(groupId)); else { params.delete("group"); params.delete("session"); }
      window.history.replaceState(null, "", `${window.location.pathname}${params.size ? `?${params}` : ""}`);
    } catch (cause) {
      if (sequence === loadSequence.current) setError(cause instanceof Error ? cause.message : "Не удалось загрузить группы");
    } finally {
      if (sequence === loadSequence.current) setLoading(false);
    }
  }, [request]);

  useEffect(() => {
    try {
      const auth: { email?: string; username?: string } = JSON.parse(localStorage.getItem("partner_auth_user") || "{}");
      if (auth.email || auth.username) setEmail((auth.email || auth.username || "").trim());
      else { setError("Войдите в кабинет партнёра"); setLoading(false); }
      const sessionId = Number(new URLSearchParams(window.location.search).get("session"));
      if (sessionId) setExpanded([sessionId]);
    } catch { setError("Не удалось прочитать данные авторизации. Войдите заново."); setLoading(false); }
  }, []);
  useEffect(() => {
    if (!email) return;
    const groupId = Number(new URLSearchParams(window.location.search).get("group")) || undefined;
    void load(groupId);
  }, [email, load]);

  const groupServices = services.filter((item) => item.is_active && item.service_type === "group");
  const selectedService = services.find((item) => String(item.id) === serviceId);
  const availableSpecialists = specialists.filter((item) => item.is_active && item.service_ids.includes(Number(serviceId)));
  const filteredGroups = groups.filter((group) => `${group.name} ${group.service_name} ${group.specialist_name}`.toLowerCase().includes(search.trim().toLowerCase()));
  const futureSessions = detail?.sessions.filter((item) => item.status === "scheduled" && new Date(item.starts_at).getTime() > Date.now()) || [];
  const availableSessions = selectableSessions(detail?.sessions || [], Date.now());
  const transferTargets = sessions.filter((session) => modal?.kind === "move" && session.service_id === detail?.service_id && session.duration_minutes === detail.duration_minutes && session.id !== modal.booking.session_id && session.status === "scheduled" && session.available_places > 0 && new Date(session.starts_at).getTime() > Date.now());
  const members = useMemo(() => {
    const map = new Map<string, GroupParticipant[]>();
    for (const booking of detail?.bookings || []) map.set(booking.client_phone, [...(map.get(booking.client_phone) || []), booking]);
    const query = memberSearch.trim().toLowerCase();
    const digits = query.replace(/\D/g, "");
    return [...map.values()].filter((bookings) => bookings.some((booking) => booking.client_name.toLowerCase().includes(query) || (digits && booking.client_phone.replace(/\D/g, "").includes(digits))));
  }, [detail, memberSearch]);

  function openModal(value: Modal) {
    requestKey.current = null; setFormError(""); setNotice(""); setModal(value);
    if (value.kind === "create") {
      setName(""); setServiceId(""); setSpecialistId(""); setCapacity(1); setCount(1); setVisits([]); setFirstTime("");
    }
    if (value.kind === "enroll") {
      setClientName(""); setPhone(""); setSelectedSessions(availableSessions.map((item) => item.id));
    }
    if (value.kind === "move") {
      setMoveMode("group"); setTargetSession(""); setServiceId(String(detail?.service_id || "")); setSpecialistId(String(detail?.specialist_id || "")); setFirstDate(value.booking.starts_at.slice(0, 10)); setFirstTime("");
    }
    if (value.kind === "lesson-move") {
      setServiceId(String(value.session.service_id)); setSpecialistId(String(value.session.specialist_id));
      setFirstDate(value.session.starts_at.slice(0, 10)); setFirstTime(timeLabel(value.session.starts_at));
    }
  }

  async function perform(path: string, body: Record<string, unknown>, method = "POST", created = false) {
    setBusy(true); setFormError(""); setNotice("");
    try {
      const result = await request<{ id: number }>(path, { method, body: JSON.stringify(body) });
      setModal(null);
      setNotice(created ? "Группа создана. Теперь можно добавить участников." : "Изменения сохранены");
      await load(created ? result.id : detail?.id);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : "Не удалось сохранить изменения";
      setFormError(message); setError(modal ? "" : message);
    } finally { setBusy(false); }
  }

  function idempotent(path: string, body: Record<string, unknown>) {
    const payload = JSON.stringify({ path, body });
    if (requestKey.current?.payload !== payload) requestKey.current = { payload, key: crypto.randomUUID() };
    return { ...body, request_id: requestKey.current.key };
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (busy || !modal) return;
    if (modal.kind === "create") {
      if (visits.length !== count || visits.some((visit) => !visit.date || !visit.time)) { setFormError("Сформируйте расписание и выберите время каждого занятия"); return; }
      const body = { name, service_id: Number(serviceId), specialist_id: Number(specialistId), capacity, sessions: visits.map((visit) => new Date(`${visit.date}T${visit.time}:00+05:00`).toISOString()) };
      void perform("groups/", idempotent("groups/", body), "POST", true);
    } else if (modal.kind === "enroll" && detail) {
      const path = `groups/${detail.id}/enroll/`;
      void perform(path, idempotent(path, { client_name: clientName, client_phone: phone, session_ids: selectedSessions }));
    } else if (modal.kind === "cancel") {
      void perform(`groups/participants/${modal.booking.id}/`, { action: "cancel" }, "PATCH");
    } else if (modal.kind === "move") {
      const body = moveMode === "group" ? { session_id: Number(targetSession) } : { specialist_id: Number(specialistId), starts_at: new Date(`${firstDate}T${firstTime}:00+05:00`).toISOString() };
      void perform(`groups/participants/${modal.booking.id}/`, { action: "move", ...body }, "PATCH");
    } else if (modal.kind === "lesson-move" || modal.kind === "lesson-cancel") {
      void perform(`groups/sessions/${modal.session.id}/`, modal.kind === "lesson-cancel" ? { action: "cancel" } : { action: "move", starts_at: new Date(`${firstDate}T${firstTime}:00+05:00`).toISOString() }, "PATCH");
    }
  }

  function participantRow(booking: GroupParticipant, movedAway = false) {
    const active = isActiveVisit(booking.status);
    return <div key={booking.id} className={`${styles.participant} ${movedAway || !active ? styles.participantMuted : ""}`}>
      <div className={styles.identity}><strong>{booking.client_name}</strong><span>{formatRuPhone(booking.client_phone)}</span>{movedAway ? <small>Перенесено на {dateLabel(booking.starts_at)}, {timeLabel(booking.starts_at)}{booking.is_individual_override ? " · отдельное время" : ""}</small> : null}</div>
      <div className={styles.participantMeta}><strong>{money(booking.final_price)}</strong><span className={`${styles.badge} ${complete(booking.status) ? styles.success : ""}`}>{complete(booking.status) ? <Check size={13} /> : null}{statusLabel(booking.status)}</span></div>
      {active && !movedAway ? <div className={styles.rowActions}>
        <button type="button" disabled={busy || loading} onClick={() => void perform(`groups/participants/${booking.id}/`, { action: "complete" }, "PATCH")}>Пришёл</button>
        <button type="button" disabled={busy || loading} onClick={() => void perform(`groups/participants/${booking.id}/`, { action: "no_show" }, "PATCH")}>Неявка</button>
        <button type="button" disabled={busy || loading} onClick={() => openModal({ kind: "move", booking })}>Перенести</button>
        <button type="button" className={styles.dangerText} disabled={busy || loading} onClick={() => openModal({ kind: "cancel", booking })}>Отменить</button>
      </div> : null}
    </div>;
  }

  return <section className={styles.page}>
    <header className={styles.header}>
      <div>{detail ? <button type="button" className={styles.back} disabled={busy} onClick={() => { setTab("sessions"); setExpanded([]); void load(); }}><ArrowLeft size={16} />Все группы</button> : <span className={styles.eyebrow}>ЗАНЯТИЯ И УЧАСТНИКИ</span>}<h1>{detail?.name || "Группы и абонементы"}</h1><p>{detail ? `${detail.service_name} · ${detail.specialist_name}` : "Создайте расписание группы, затем добавляйте клиентов на нужные занятия."}</p></div>
      <div className={styles.headerActions}><Link href="/partner/dashboard/schedule" className={styles.secondary}><CalendarDays size={17} />Расписание</Link><button type="button" className={styles.primary} disabled={loading || busy || !email || (Boolean(detail) && !availableSessions.length)} onClick={() => openModal(detail ? { kind: "enroll" } : { kind: "create" })}><Plus size={18} />{detail ? "Добавить участника" : "Создать группу"}</button></div>
    </header>
    {error ? <div className={styles.error} role="alert">{error}<button type="button" onClick={() => void load(detail?.id)}>Повторить загрузку</button></div> : null}
    {notice ? <div className={styles.notice} role="status"><Check size={18} />{notice}</div> : null}
    {loading ? <p role="status" className={styles.loading}>Загрузка групп…</p> : null}
    {!detail ? <>
      <section className={styles.stats} aria-label="Обзор групп"><div><Users size={19} /><span>Группы<strong>{groups.length}</strong></span></div><div><CalendarDays size={19} /><span>Будущие занятия<strong>{groups.reduce((sum, group) => sum + group.future_session_count, 0)}</strong></span></div><div><Clock3 size={19} /><span>Группа может быть пустой<small>Клиентов можно добавить позже</small></span></div></section>
      <label className={styles.search}><Search size={18} /><input aria-label="Поиск группы" placeholder="Группа, услуга или специалист" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
      <section className={styles.cards} aria-label="Группы">
        {filteredGroups.map((group) => <button type="button" className={styles.groupCard} key={group.id} disabled={busy || loading} onClick={() => { setTab("sessions"); setExpanded([]); void load(group.id); }}>
          <div className={styles.cardTop}><span className={styles.groupIcon}><Users size={23} /></span><span className={styles.badge}>{group.future_session_count ? "Набор открыт" : "Занятия завершены"}</span></div>
          <h2>{group.name}</h2><p>{group.service_name}</p><span className={styles.specialist}>{group.specialist_name}</span>
          <div className={styles.cardFacts}><span><CalendarDays size={15} />{lessonCount(group.session_count)}</span><span><Users size={15} />До {group.capacity} человек</span></div>
          <div className={styles.cardBottom}><span>{group.next_session ? <>Ближайшее занятие<strong>{dateLabel(group.next_session)}, {timeLabel(group.next_session)}</strong></> : "Нет будущих занятий"}</span><ArrowRight size={19} /></div>
        </button>)}
      </section>
      {!loading && !error && !filteredGroups.length ? <section className={styles.empty}><span className={styles.emptyIcon}><Users size={32} /></span><h2>{search ? "Группы не найдены" : "Начните с пустой группы"}</h2><p>{search ? "Попробуйте другое название или имя специалиста." : "Выберите услугу, специалиста и даты. Записи клиентов появятся только после добавления участников."}</p>{!search ? <button type="button" className={styles.primary} onClick={() => openModal({ kind: "create" })}><Plus size={17} />Создать группу</button> : null}</section> : null}
    </> : <>
      <section className={styles.detailFacts}><span><CalendarDays size={18} />{lessonCount(detail.session_count)}</span><span><Clock3 size={18} />{detail.duration_minutes} минут · время Алматы</span><span><Users size={18} />До {detail.capacity} человек на занятии</span><strong>{detail.price_mode === "total" ? `${money(detail.price)} за весь цикл` : `${money(detail.price)} за занятие`}</strong></section>
      <div className={styles.tabs} role="tablist" aria-label="Содержимое группы"><button type="button" role="tab" aria-selected={tab === "sessions"} onClick={() => setTab("sessions")}>Занятия <span>{detail.sessions.length}</span></button><button type="button" role="tab" aria-selected={tab === "members"} onClick={() => setTab("members")}>Участники <span>{new Set(detail.bookings.map((booking) => booking.client_phone)).size}</span></button></div>
      {tab === "sessions" ? <section className={styles.lessons} aria-label="Занятия группы">{detail.sessions.map((session, index) => {
        const opened = expanded.includes(session.id);
        const moved = detail.bookings.filter((booking) => booking.original_session_id === session.id && booking.session_id !== session.id);
        const isPast = new Date(session.starts_at).getTime() <= Date.now();
        return <article key={session.id} className={styles.lesson}>
          <button type="button" className={styles.lessonHeader} aria-expanded={opened} onClick={() => setExpanded((current) => current.includes(session.id) ? current.filter((id) => id !== session.id) : [...current, session.id])}>
            <span className={styles.lessonNumber}>{String(index + 1).padStart(2, "0")}</span><span className={styles.lessonDate}><strong>{dateLabel(session.starts_at)}</strong><small>{timeLabel(session.starts_at)} · {session.duration_minutes} мин</small></span>
            <span className={styles.lessonSeats}><strong>{session.occupied_places} / {session.capacity}</strong><small>{session.status === "cancelled" ? "Отменено" : isPast ? "Прошедшее занятие" : session.occupied_places ? `Свободно: ${session.available_places}` : "Пока без участников"}</small></span><ChevronDown size={19} className={opened ? styles.chevronOpen : ""} />
          </button>
          {opened ? <div className={styles.lessonBody}>
            {session.original_starts_at && session.original_starts_at !== session.starts_at ? <p className={styles.lessonChange}><Clock3 size={14} />Разовый перенос с {dateLabel(session.original_starts_at)}, {timeLabel(session.original_starts_at)}. Остальные занятия не изменены.</p> : null}
            {!isPast && session.status === "scheduled" ? <div className={styles.lessonActions}><span>Для всего занятия</span><button type="button" disabled={busy || loading} onClick={() => openModal({ kind: "lesson-move", session })}><Clock3 size={14} />Разовый перенос</button><button type="button" className={styles.dangerText} disabled={busy || loading} onClick={() => openModal({ kind: "lesson-cancel", session })}>Отменить занятие</button></div> : null}
            {session.participants.length ? session.participants.map((booking) => participantRow(booking)) : <div className={styles.lessonEmpty}><Users size={21} /><span>{session.status === "cancelled" ? "Занятие отменено. Новые участники не записываются." : "Пока никто не записан. Занятие уже есть в расписании."}</span></div>}{moved.length ? <div className={styles.movedList}><small>Перенесённые посещения</small>{moved.map((booking) => participantRow(booking, true))}</div> : null}{!isPast && session.status === "scheduled" && session.available_places > 0 ? <button type="button" className={styles.textButton} disabled={busy || loading} onClick={() => { openModal({ kind: "enroll" }); setSelectedSessions([session.id]); }}><Plus size={15} />Записать на это занятие</button> : null}</div> : null}
        </article>;
      })}</section> : <section className={styles.members}>
        <label className={styles.search}><Search size={18} /><input aria-label="Поиск участника" placeholder="Имя или телефон клиента" value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} /></label>
        {members.map((bookings) => <details className={styles.memberCard} key={bookings[0].client_phone}><summary><span className={styles.memberAvatar}>{bookings[0].client_name.slice(0, 1).toUpperCase()}</span><span><strong>{bookings[0].client_name}</strong><small>{formatRuPhone(bookings[0].client_phone)}</small></span><span className={styles.memberProgress}>Посетил: {bookings.filter((item) => complete(item.status)).length} / {bookings.length}<small>Будущих записей: {bookings.filter((item) => isActiveVisit(item.status) && new Date(item.starts_at).getTime() > Date.now()).length}</small></span><ChevronDown size={18} /></summary><div className={styles.memberVisits}>{bookings.map((booking) => <div key={booking.id}><p className={styles.visitDate}>{dateLabel(booking.starts_at)}, {timeLabel(booking.starts_at)}{booking.is_individual_override ? " · отдельное время" : booking.is_moved ? " · перенос" : ""}</p>{participantRow(booking)}</div>)}</div></details>)}
        {!members.length ? <div className={styles.empty}><Users size={30} /><h2>{memberSearch ? "Участники не найдены" : "В группе пока нет участников"}</h2><p>{memberSearch ? "Попробуйте другое имя или телефон." : "Добавьте клиента и выберите занятия, которые он будет посещать."}</p></div> : null}
      </section>}
    </>}

    {modal ? <Dialog title={modal.kind === "create" ? "Новая группа" : modal.kind === "enroll" ? "Добавить участника" : modal.kind === "move" ? "Перенести клиента" : modal.kind === "lesson-move" ? "Разовый перенос занятия" : modal.kind === "lesson-cancel" ? "Отменить занятие группы" : "Отменить посещение"} busy={busy} onClose={() => setModal(null)}>
      <form onSubmit={submit}><div className={styles.dialogBody}><fieldset disabled={busy} className={styles.formFields}>
        {modal.kind === "create" ? <>
          <div className={styles.stepHint}><Users size={20} /><span><strong>Сначала группа — потом участники</strong><small>Создайте занятия без привязки к клиенту.</small></span></div>
          {!groupServices.length ? <p className={styles.error}>Нет групповых услуг. <Link href="/partner/dashboard/manage">Создайте групповую услугу</Link> в разделе услуг.</p> : null}
          <label>Название группы<input required maxLength={120} placeholder="Например: Йога · утренняя группа" value={name} onChange={(event) => setName(event.target.value)} /></label>
          <label>Групповая услуга<select required value={serviceId} onChange={(event) => {
            const service = services.find((item) => String(item.id) === event.target.value);
            setServiceId(event.target.value); setSpecialistId(""); setFirstTime(""); setVisits([]);
            setCount(service?.is_pass ? service.visit_count : 1); setCapacity(service?.details.max_people || 1);
          }}><option value="">Выберите услугу</option>{groupServices.map((service) => <option key={service.id} value={service.id}>{service.name}{service.is_pass ? ` · абонемент, ${lessonCount(service.visit_count)}` : ""}</option>)}</select></label>
          <div className={styles.formGrid}><label>Специалист<select required value={specialistId} onChange={(event) => { setSpecialistId(event.target.value); setFirstTime(""); setVisits([]); }}><option value="">Выберите специалиста</option>{availableSpecialists.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><label>Мест в группе<input type="number" required min={1} max={selectedService?.details.max_people || 1} value={capacity} onChange={(event) => setCapacity(Number(event.target.value))} /></label></div>
          <div className={styles.formGrid}><label>Количество занятий<input type="number" required min={1} max={365} readOnly={selectedService?.is_pass} value={count} onChange={(event) => { setCount(Number(event.target.value)); setVisits([]); }} /></label><label>Цена<span className={styles.pricePreview}>{money(selectedService?.price || 0)} {selectedService?.is_pass && selectedService.pass_price_mode === "total" ? "за весь цикл" : "за занятие"}</span></label></div>
          <h3>Расписание занятий</h3><div className={styles.formGrid}><label>Первая дата<input type="date" required min={dateInput(new Date())} value={firstDate} onChange={(event) => { setFirstDate(event.target.value); setFirstTime(""); }} /></label><label>Начало · Алматы<AvailableTimeSelect reserveGroup date={firstDate} specialistId={specialistId} serviceIds={serviceId} phone="" partnerEmail={email} value={firstTime} onChange={setFirstTime} /></label></div>
          {selectedService && specialistId ? <PassVisitEditor variant="group" count={count} startDate={firstDate} startTime={firstTime} specialistId={specialistId} serviceId={serviceId} phone="" partnerEmail={email} visits={visits} onChange={setVisits} /> : null}
        </> : modal.kind === "enroll" && detail ? <>
          <p className={styles.context}>{detail.name} · {detail.specialist_name}</p>
          <div className={styles.formGrid}><label>Имя клиента<input required maxLength={120} value={clientName} onChange={(event) => setClientName(event.target.value)} placeholder="Имя и фамилия" /></label><label>Телефон<input required type="tel" value={phone} onChange={(event) => setPhone(formatRuPhone(event.target.value))} placeholder="+7 (___) ___-__-__" /></label></div>
          <div className={styles.sectionHeading}><h3>Занятия участника</h3><button type="button" className={styles.textButton} onClick={() => setSelectedSessions(selectedSessions.length === availableSessions.length ? [] : availableSessions.map((item) => item.id))}>{selectedSessions.length === availableSessions.length ? "Снять выбор" : "Выбрать доступные"}</button></div>
          <p className={styles.context}>Выбрано: {selectedSessions.length} из {futureSessions.length}. Можно оставить только нужные даты.</p>
          <div className={styles.sessionChoices}>{futureSessions.map((session) => <label key={session.id} className={`${styles.sessionChoice} ${selectedSessions.includes(session.id) ? styles.sessionChosen : ""}`}><input type="checkbox" disabled={!session.available_places} checked={selectedSessions.includes(session.id)} onChange={() => setSelectedSessions((current) => current.includes(session.id) ? current.filter((id) => id !== session.id) : [...current, session.id])} /><span><strong>{dateLabel(session.starts_at)}</strong><small>{timeLabel(session.starts_at)} · {session.available_places ? `Свободно: ${session.available_places}` : "Нет мест"}</small></span><strong>{money(session.base_price)}</strong></label>)}</div>
          <div className={styles.total}><span>Стоимость выбранных посещений<small>Без скидки платформы. Это сумма записей, не подтверждение оплаты.</small></span><strong>{money(enrollmentTotal(detail.sessions, selectedSessions))}</strong></div>
        </> : modal.kind === "move" && detail ? <>
          <div className={styles.stepHint}><span className={styles.memberAvatar}>{modal.booking.client_name.slice(0, 1)}</span><span><strong>{modal.booking.client_name}</strong><small>{dateLabel(modal.booking.starts_at)}, {timeLabel(modal.booking.starts_at)}</small></span></div>
          <p className={styles.context}>Переносится только это посещение. Расписание группы и записи остальных клиентов не изменятся.</p>
          <div className={styles.modeButtons}><button type="button" aria-pressed={moveMode === "group"} onClick={() => setMoveMode("group")}>В другое занятие</button><button type="button" aria-pressed={moveMode === "separate"} onClick={() => setMoveMode("separate")}>На отдельное время</button></div>
          {moveMode === "group" ? <><label>Занятие для переноса<select required value={targetSession} onChange={(event) => setTargetSession(event.target.value)}><option value="">Выберите группу и дату</option>{transferTargets.map((session) => <option key={session.id} value={session.id}>{session.group_name} · {dateLabel(session.starts_at)}, {timeLabel(session.starts_at)} · {session.specialist_name} · мест: {session.available_places}</option>)}</select></label>{!transferTargets.length ? <p className={styles.context}>Нет подходящих занятий со свободными местами. Можно выбрать отдельное время.</p> : null}</> : <><label>Специалист<select required value={specialistId} onChange={(event) => { setSpecialistId(event.target.value); setFirstTime(""); }}><option value="">Выберите специалиста</option>{availableSpecialists.map((item) => <option key={item.id} value={item.id}>{item.full_name}</option>)}</select></label><div className={styles.formGrid}><label>Дата<input type="date" min={dateInput(new Date())} required value={firstDate} onChange={(event) => { setFirstDate(event.target.value); setFirstTime(""); }} /></label><label>Свободное время · Алматы<AvailableTimeSelect reserveGroup excludeBookingId={modal.booking.id} date={firstDate} specialistId={specialistId} serviceIds={serviceId} phone={modal.booking.client_phone} partnerEmail={email} value={firstTime} onChange={setFirstTime} /></label></div></>}
          <p className={styles.preservedPrice}>Стоимость посещения сохранится: <strong>{money(modal.booking.base_price)}</strong>. Для мобильной записи скидка проверяется заново на выбранную дату.</p>
        </> : modal.kind === "lesson-move" || modal.kind === "lesson-cancel" ? <>
          <div className={styles.stepHint}><CalendarDays size={23} /><span><strong>{modal.session.group_name}</strong><small>{dateLabel(modal.session.starts_at)}, {timeLabel(modal.session.starts_at)} · участников: {modal.session.occupied_places}</small></span></div>
          {modal.kind === "lesson-move" ? <>
            <p className={styles.scopeNotice}>Изменится только это занятие и время его участников. Все остальные даты группы останутся по прежнему расписанию.</p>
            <div className={styles.formGrid}><label>Дата занятия<input type="date" required min={dateInput(new Date())} value={firstDate} onChange={(event) => { setFirstDate(event.target.value); setFirstTime(""); }} /></label><label>Новое время · Алматы<AvailableTimeSelect reserveGroup excludeSessionId={modal.session.id} date={firstDate} specialistId={specialistId} serviceIds={serviceId} phone="" partnerEmail={email} value={firstTime} onChange={setFirstTime} /></label></div>
            <p className={styles.context}>Проверим занятость преподавателя и каждого участника. Если у кого-то есть пересечение, перенос не сохранится ни для кого. Индивидуальные переносы на другое время не затрагиваются.</p>
          </> : <p className={styles.scopeNotice}>Отменится это занятие и активные записи его участников. Другие занятия группы и отдельные переносы клиентов сохранятся. Время преподавателя освободится.</p>}
        </> : modal.kind === "cancel" ? <><p><strong>{modal.booking.client_name}</strong></p><p>{dateLabel(modal.booking.starts_at)}, {timeLabel(modal.booking.starts_at)}</p><p className={styles.context}>Отменится только это посещение клиента. Другие даты абонемента, участники и само занятие останутся без изменений.</p></> : null}
      </fieldset>{formError ? <div className={styles.error} role="alert">{formError}</div> : null}</div>
      <footer className={styles.dialogFooter}><button type="button" className={styles.secondary} disabled={busy} onClick={() => setModal(null)}>Назад</button><button type="submit" className={modal.kind === "cancel" || modal.kind === "lesson-cancel" ? styles.danger : styles.primary} disabled={busy || (modal.kind === "create" && (!groupServices.length || visits.length !== count || !count || visits.some((visit) => !visit.time))) || (modal.kind === "enroll" && !selectedSessions.length) || (modal.kind === "move" && (moveMode === "group" ? !targetSession : !firstTime)) || (modal.kind === "lesson-move" && !firstTime)}>{busy ? "Сохранение…" : modal.kind === "create" ? "Создать пустую группу" : modal.kind === "enroll" ? `Записать · ${lessonCount(selectedSessions.length)}` : modal.kind === "move" ? "Перенести клиента" : modal.kind === "lesson-move" ? "Перенести только это занятие" : modal.kind === "lesson-cancel" ? "Отменить это занятие" : "Отменить посещение"}</button></footer></form>
    </Dialog> : null}
  </section>;
}
