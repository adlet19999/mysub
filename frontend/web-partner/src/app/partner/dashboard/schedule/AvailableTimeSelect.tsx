"use client";

import { useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

type Props = {
  date: string;
  specialistId: string;
  serviceIds: string;
  phone: string;
  partnerEmail: string;
  excludeBookingId?: number | null;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
};

export default function AvailableTimeSelect(props: Props) {
  const { date, specialistId, serviceIds, phone, partnerEmail, excludeBookingId, value, onChange, disabled, className } = props;
  const [result, setResult] = useState<{ key: string; slots: string[]; error: string }>({ key: "", slots: [], error: "" });
  const [retry, setRetry] = useState(0);
  const changeRef = useRef(onChange);
  const valueRef = useRef(value);
  changeRef.current = onChange;
  valueRef.current = value;
  const params = new URLSearchParams({ date, specialist_id: specialistId, service_ids: serviceIds });
  if (phone.replace(/\D/g, "").length === 11) params.set("client_phone", phone);
  if (excludeBookingId) params.set("exclude_booking_id", String(excludeBookingId));
  const query = params.toString();
  const key = `${partnerEmail}:${query}`;
  const ready = Boolean(date && specialistId && serviceIds && partnerEmail);

  useEffect(() => {
    if (!ready || disabled) return;
    const controller = new AbortController();
    void (async () => {
      try {
        const response = await fetch(`${API_BASE}/partner/bookings/availability/?${query}`, {
          headers: { "X-Partner-Email": partnerEmail, "X-Tenant": TENANT },
          cache: "no-store",
          signal: controller.signal,
        });
        const payload: { slots?: unknown; message?: string } = await response.json();
        if (!response.ok) throw new Error(payload.message || "Не удалось получить свободное время");
        if (!Array.isArray(payload.slots) || !payload.slots.every((slot): slot is string => typeof slot === "string")) {
          throw new Error("Некорректный ответ сервера со свободным временем");
        }
        if (controller.signal.aborted) return;
        setResult({ key, slots: payload.slots, error: "" });
        if (valueRef.current && !payload.slots.includes(valueRef.current)) changeRef.current("");
      } catch (error) {
        if (controller.signal.aborted) return;
        setResult({ key, slots: [], error: error instanceof Error ? error.message : "Не удалось получить свободное время" });
      }
    })();
    return () => controller.abort();
  }, [ready, disabled, query, key, partnerEmail, retry]);

  if (disabled) return <select className={className} disabled value={value}><option value={value}>{value}</option></select>;
  const loaded = ready && result.key === key;
  return <>
    <select className={className} aria-label="Свободное время" required disabled={!loaded || Boolean(result.error)} value={loaded && result.slots.includes(value) ? value : ""} onChange={(event) => onChange(event.target.value)}>
      <option value="">{!ready ? "Выберите услугу, специалиста и дату" : !loaded ? "Загрузка..." : result.error ? "Ошибка загрузки" : result.slots.length ? "Выберите время" : "Нет свободного времени"}</option>
      {loaded && !result.error ? result.slots.map((slot) => <option key={slot} value={slot}>{slot}</option>) : null}
    </select>
    {loaded && result.error ? <span role="alert">{result.error} <button type="button" onClick={() => {
      setResult({ key: "", slots: [], error: "" });
      setRetry((current) => current + 1);
    }}>Повторить загрузку времени</button></span> : null}
  </>;
}
