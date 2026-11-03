"use client";

import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { RestaurantReservation } from "../../../../lib/restaurant";
import { readApiResponse } from "../../../../lib/apiResponse";
import { formatRuPhone } from "../../../../lib/phone";
import AvailableTimeSelect from "./AvailableTimeSelect";
import styles from "../groups/page.module.css";
import restaurantStyles from "./RestaurantBooking.module.css";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";
type ReservationBooking = { id: number; service_name: string; starts_at: string; client_name: string; client_phone: string; status: string; final_price?: string; restaurant?: RestaurantReservation | null };
type Service = { id: number; name: string; price: string | null; is_active: boolean; service_type: string; is_pass: boolean };
const dateTime = (value: string) => new Intl.DateTimeFormat("ru-RU", { dateStyle: "short", timeStyle: "short", timeZone: "Asia/Almaty" }).format(new Date(value));

function RestaurantDialog({ title, busy, onClose, children }: { title: string; busy: boolean; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { ref.current?.close(); document.body.style.overflow = overflow; };
  }, []);
  return <dialog ref={ref} className={styles.dialog} onCancel={(event) => { event.preventDefault(); if (!busy) onClose(); }} aria-label={title}>
    <header className={styles.dialogHeader}><h2>{title}</h2><button type="button" className={styles.iconButton} disabled={busy} onClick={onClose} aria-label="Закрыть">×</button></header>{children}
  </dialog>;
}

async function save(email: string, path: string, body: Record<string, unknown>, method: string) {
  const response = await fetch(`${API_BASE}/partner/${path}`, {
    method, headers: { "Content-Type": "application/json", "X-Partner-Email": email, "X-Tenant": TENANT },
    body: JSON.stringify(body),
  });
  const payload = await readApiResponse(response, "Не удалось сохранить бронь");
  if (!payload || typeof payload !== "object" || !("id" in payload) || typeof payload.id !== "number") {
    throw new Error("Сервер не подтвердил изменение брони. Обновите расписание перед повторной попыткой.");
  }
}

export function RestaurantBookingForm({ email, services, date: initialDate, booking, onClose, onSaved }: { email: string; services: Service[]; date: string; booking?: ReservationBooking; onClose: () => void; onSaved: () => Promise<void> }) {
  const [name, setName] = useState(booking?.client_name || "");
  const [phone, setPhone] = useState(booking?.client_phone || "");
  const [guests, setGuests] = useState(booking?.restaurant?.party_size || 2);
  const [serviceId, setServiceId] = useState(String(services.find((service) => service.name === booking?.service_name)?.id || ""));
  const [date, setDate] = useState(booking?.starts_at.slice(0, 10) || initialDate);
  const [time, setTime] = useState(booking?.starts_at.slice(11, 16) || "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (error) requestAnimationFrame(() => errorRef.current?.scrollIntoView({ block: "center" })); }, [error]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError("");
    if (!name.trim() || !/^\+7\d{10}$/.test(phone.replace(/[\s()-]/g, "")) || !serviceId || !date || !time || !Number.isInteger(guests) || guests < 1 || guests > 1000) {
      setError("Укажите клиента, полный телефон, предложение, число гостей, дату и свободное время");
      return;
    }
    setBusy(true);
    try {
      const starts_at = `${date}T${time}:00+05:00`;
      if (booking) {
        await save(email, `bookings/${booking.id}/restaurant/`, { action: booking.restaurant ? "move" : "assign_table", starts_at, party_size: guests, service_id: Number(serviceId) }, "PATCH");
      } else {
        const service = services.find((item) => String(item.id) === serviceId);
        if (!service) throw new Error("Предложение недоступно");
        await save(email, "bookings/", { service_name: service.name, service_ids: [service.id], client_name: name.trim(), client_phone: phone, starts_at, party_size: guests }, "POST");
      }
      await onSaved();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Не удалось сохранить бронь");
    } finally { setBusy(false); }
  }
  return <RestaurantDialog title={booking ? "Перенести бронь столика" : "Новая бронь столика"} busy={busy} onClose={onClose}>
    <form noValidate onSubmit={submit}>
      <div className={styles.dialogBody}><fieldset disabled={busy} className={styles.formFields}>
        <p className={styles.context}>{booking && !booking.restaurant ? "Существующая запись будет привязана к свободному столику. История и сохранённая стоимость останутся." : "Столик назначается автоматически по числу гостей и занятости на два часа."}</p>
        <div className={styles.formGrid}><label>Клиент<input disabled={Boolean(booking)} value={name} onChange={(event) => setName(event.target.value)} maxLength={120} /></label><label>Телефон<input disabled={Boolean(booking)} type="tel" value={phone} onChange={(event) => setPhone(formatRuPhone(event.target.value))} placeholder="+7 (___) ___-__-__" /></label></div>
        <div className={styles.formGrid}><label>Предложение<select disabled={Boolean(booking?.restaurant)} value={serviceId} onChange={(event) => { setServiceId(event.target.value); setTime(""); }}><option value="">Выберите предложение</option>{services.filter((item) => item.is_active && item.service_type === "individual" && !item.is_pass).map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><label>Количество гостей<input type="number" min={1} max={1000} step={1} value={guests} onChange={(event) => setGuests(Number(event.target.value))} /></label></div>
        <div className={styles.formGrid}><label>Дата<input type="date" min={new Date().toLocaleDateString("en-CA")} value={date} onChange={(event) => setDate(event.target.value)} /></label><label>Время начала<AvailableTimeSelect restaurant partySize={guests} date={date} serviceIds={serviceId} specialistId="" phone={phone} partnerEmail={email} value={time} onChange={setTime} excludeBookingId={booking?.id} /></label></div>
        {error ? <p ref={errorRef} className={styles.error} role="alert">{error}</p> : null}
      </fieldset></div>
      <footer className={`${styles.dialogFooter} ${restaurantStyles.footer}`}><button type="button" className={styles.secondary} onClick={onClose} disabled={busy}>Отмена</button><button type="submit" className={styles.primary} disabled={busy}>{busy ? "Сохранение..." : booking ? "Перенести бронь" : "Забронировать столик"}</button></footer>
    </form>
  </RestaurantDialog>;
}

export function RestaurantBookingDetails({ email, booking, onClose, onSaved, onMove }: { email: string; booking: ReservationBooking; onClose: () => void; onSaved: () => Promise<void>; onMove: () => void }) {
  const [amount, setAmount] = useState(booking.final_price || "0");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);
  useEffect(() => { if (error) requestAnimationFrame(() => errorRef.current?.scrollIntoView({ block: "center" })); }, [error]);
  const reservation = booking.restaurant;
  if (!reservation) return null;
  async function act(action: string) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      await save(email, `bookings/${booking.id}/restaurant/`, { action, paid_amount: amount.replace(",", ".") }, "PATCH");
      await onSaved(); onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось изменить бронь"); }
    finally { setBusy(false); }
  }
  return <RestaurantDialog title="Бронь столика" busy={busy} onClose={onClose}>
    <div className={styles.dialogBody}>
      <h3>{booking.client_name} · {reservation.party_size} гостей</h3><p>{formatRuPhone(booking.client_phone)}</p>
      <p><strong>{reservation.table_name}</strong> · вместимость {reservation.table_capacity}</p>
      <p>{dateTime(booking.starts_at)} — {dateTime(reservation.ends_at)}</p>
      <p className={styles.context}>{booking.status === "arrived" ? "Гости за столиком. Бронь продлевается автоматически до завершения обслуживания." : booking.status === "completed" ? `Обслуживание завершено. Получено: ${reservation.paid_amount} ₸` : booking.status === "no_show" ? "Неявка. Запись сохранена в истории." : booking.status === "cancelled" ? "Бронь отменена. Запись сохранена в истории." : "Ожидаем гостей. Подтвердите приход, когда они займут столик."}</p>
      {reservation.notice ? <p className={styles.error} role="alert">{reservation.notice}</p> : null}
      {reservation.segments.length > 1 ? <details><summary>Продления: {reservation.segments.length - 1}</summary>{reservation.segments.filter((segment) => segment.is_extension).map((segment) => <p key={segment.starts_at}>{dateTime(segment.starts_at)} — {dateTime(segment.ends_at)}</p>)}</details> : null}
      {booking.status === "arrived" ? <label className={styles.formFields}>Полученная оплата (₸)<input type="number" min={0} step="0.01" value={amount} onChange={(event) => setAmount(event.target.value)} disabled={busy} /></label> : null}
      {error ? <p ref={errorRef} className={styles.error} role="alert">{error}</p> : null}
    </div>
    <footer className={`${styles.dialogFooter} ${restaurantStyles.footer}`}>
      {booking.status === "booked" ? <><button type="button" disabled={busy} className={styles.secondary} onClick={onMove}>Перенести</button><button type="button" disabled={busy} className={styles.secondary} onClick={() => void act("no_show")}>Неявка</button><button type="button" disabled={busy} className={styles.secondary} onClick={() => void act("cancel")}>Отменить бронь</button><button type="button" disabled={busy || new Date(booking.starts_at).getTime() > Date.now()} className={styles.primary} onClick={() => void act("arrive")}>Гости пришли</button></> : booking.status === "arrived" ? <button type="button" disabled={busy} className={styles.primary} onClick={() => void act("finish")}>Оплата получена · Завершить</button> : <button type="button" className={styles.secondary} onClick={onClose}>Закрыть</button>}
    </footer>
  </RestaurantDialog>;
}
