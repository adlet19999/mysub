"use client";

import { Dispatch, SetStateAction, useState } from "react";
import AvailableTimeSelect from "./AvailableTimeSelect";
import styles from "./page.module.css";

export type PassVisit = { date: string; time: string };

type Props = {
  count: number;
  startDate: string;
  startTime: string;
  specialistId: string;
  serviceId: string;
  phone: string;
  partnerEmail: string;
  visits: PassVisit[];
  onChange: Dispatch<SetStateAction<PassVisit[]>>;
};

export default function PassVisitEditor(props: Props) {
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [error, setError] = useState("");
  function generate() {
    if (!props.startDate || !props.startTime) {
      setError("Сначала выберите дату и свободное время первого посещения");
      return;
    }
    const date = new Date(`${props.startDate}T12:00:00`);
    const days = weekdays.length ? weekdays : [date.getDay()];
    const visits: PassVisit[] = [];
    while (visits.length < props.count) {
      if (days.includes(date.getDay())) {
        visits.push({ date: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`, time: props.startTime });
      }
      date.setDate(date.getDate() + 1);
    }
    props.onChange(visits);
    setError("");
  }
  function update(index: number, patch: Partial<PassVisit>) {
    props.onChange((visits) => visits.map((visit, current) => current === index ? { ...visit, ...patch } : visit));
  }
  return <section className={styles.passEditor} aria-label="Посещения абонемента">
    <strong>Абонемент · посещений: {props.count}</strong>
    <p>Выберите дни недели и заполните даты. Без выбора дней — еженедельно. Дату и время каждого посещения можно изменить.</p>
    <div className={styles.passWeekdays}>{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((label, index) => {
      const day = (index + 1) % 7;
      return <label key={day}><input type="checkbox" checked={weekdays.includes(day)} onChange={() => setWeekdays((current) => current.includes(day) ? current.filter((value) => value !== day) : [...current, day])} />{label}</label>;
    })}</div>
    <button type="button" className={styles.addMoreButton} onClick={generate}>Заполнить даты ({props.count})</button>
    {error ? <p role="alert">{error}</p> : null}
    {props.visits.map((visit, index) => <div className={styles.passVisitRow} key={index}>
      <span>#{index + 1}</span>
      <input aria-label={`Дата посещения ${index + 1}`} type="date" required value={visit.date} onChange={(event) => update(index, { date: event.target.value, time: "" })} />
      <AvailableTimeSelect date={visit.date} value={visit.time} onChange={(time) => update(index, { time })} specialistId={props.specialistId} serviceIds={props.serviceId} phone={props.phone} partnerEmail={props.partnerEmail} />
    </div>)}
    <p>Все посещения сохраняются вместе. Конфликт хотя бы одной даты отменяет создание всего абонемента. Неявка не удаляет посещение; его можно перенести.</p>
  </section>;
}
