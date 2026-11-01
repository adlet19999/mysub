"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { BusinessTable } from "../../../../lib/restaurant";
import styles from "./page.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

export default function TablesPage() {
  const [email, setEmail] = useState("");
  const [tables, setTables] = useState<BusinessTable[]>([]);
  const [name, setName] = useState("");
  const [capacity, setCapacity] = useState(2);
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  async function request(path: string, init?: RequestInit) {
    const response = await fetch(`${API_BASE}/partner/${path}`, { ...init, cache: "no-store", headers: { "Content-Type": "application/json", "X-Partner-Email": email, "X-Tenant": TENANT } });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.message || "Не удалось выполнить действие со столиком");
    return payload;
  }
  async function load() {
    setLoading(true); setError("");
    try {
      const payload: unknown = await request("tables/");
      if (!Array.isArray(payload)) throw new Error("Некорректный список столиков");
      setTables(payload);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось загрузить столики"); }
    finally { setLoading(false); }
  }
  useEffect(() => {
    try {
      const user: { email?: string; username?: string } = JSON.parse(localStorage.getItem("partner_auth_user") || "{}");
      const value = user.email || user.username;
      if (!value) throw new Error("Войдите в кабинет партнёра");
      setEmail(value);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось прочитать авторизацию"); setLoading(false); }
  }, []);
  useEffect(() => { if (email) void load(); }, [email]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (!name.trim() || !Number.isInteger(capacity) || capacity < 1 || capacity > 1000) { setError("Укажите название и целую вместимость от 1 до 1000"); return; }
    setBusy(true); setError("");
    try {
      await request(editing ? `tables/${editing}/` : "tables/", { method: editing ? "PATCH" : "POST", body: JSON.stringify({ name: name.trim(), capacity }) });
      setName(""); setCapacity(2); setEditing(null); await load();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось сохранить столик"); }
    finally { setBusy(false); }
  }
  async function toggle(table: BusinessTable) {
    setBusy(true); setError("");
    try { await request(`tables/${table.id}/`, { method: "PATCH", body: JSON.stringify({ is_active: !table.is_active }) }); await load(); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось изменить столик"); }
    finally { setBusy(false); }
  }
  return <section className={styles.page}>
    <header className={styles.header}><div><h1>Столики</h1><p>Клиент указывает число гостей — свободный столик подходящей вместимости назначается автоматически.</p></div><Link href="/partner/dashboard/schedule">Расписание и брони</Link></header>
    <form className={styles.editor} noValidate onSubmit={submit}><h2>{editing ? "Редактировать столик" : "Добавить столик"}</h2><div className={styles.fields}><label>Название<input value={name} maxLength={120} disabled={busy} placeholder="Например: Столик у окна № 1" onChange={(event) => setName(event.target.value)} /></label><label>Количество мест<input type="number" min={1} max={1000} step={1} disabled={busy} value={capacity} onChange={(event) => setCapacity(Number(event.target.value))} /></label><button disabled={busy || loading} type="submit">{busy ? "Сохранение..." : editing ? "Сохранить" : "Добавить столик"}</button>{editing ? <button type="button" disabled={busy} onClick={() => { setEditing(null); setName(""); setCapacity(2); }}>Отмена</button> : null}</div></form>
    {error ? <p className={styles.error} role="alert">{error} <button type="button" disabled={busy} onClick={() => void load()}>Обновить список</button></p> : null}
    {loading ? <p>Загрузка столиков...</p> : <div className={styles.cards}>{tables.map((table) => <article className={`${styles.card} ${!table.is_active ? styles.archived : ""}`} key={table.id}><span className={styles.seats}>{table.capacity} мест</span><h2>{table.name}</h2><p>{table.is_active ? "Доступен для бронирования" : "В архиве"}</p><div className={styles.actions}><button type="button" disabled={busy} onClick={() => { setEditing(table.id); setName(table.name); setCapacity(table.capacity); window.scrollTo({ top: 0, behavior: "smooth" }); }}>Изменить</button><button type="button" disabled={busy} onClick={() => void toggle(table)}>{table.is_active ? "В архив" : "Вернуть"}</button></div></article>)}</div>}
    {!loading && !error && !tables.length ? <p className={styles.empty}>Добавьте столики и количество мест. После этого клиенты смогут бронировать свободное время.</p> : null}
  </section>;
}
