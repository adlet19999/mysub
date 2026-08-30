"use client";

import { FormEvent, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import styles from "./page.module.css";

export default function ResetPasswordPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const uid = (searchParams.get("uid") || "").trim();
  const token = (searchParams.get("token") || "").trim();
  const hasTokenParams = useMemo(() => Boolean(uid && token), [uid, token]);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!hasTokenParams) {
      setError("Ссылка недействительна");
      return;
    }
    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    setLoading(true);
    setError("");
    setMessage("");

    try {
      const response = await fetch("/api/partner/password/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ uid, token, newPassword: password }),
      });

      const payload = (await response.json()) as { message?: string };
      if (!response.ok) {
        setError(payload.message || "Не удалось обновить пароль");
        return;
      }

      setMessage(payload.message || "Пароль обновлен");
      setTimeout(() => router.push("/partner"), 1200);
    } catch {
      setError("Не удалось подключиться к серверу");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.shell}>
      <div className={styles.card}>
        <h1 className={styles.title}>Новый пароль</h1>
        <p className={styles.subtitle}>Задайте новый пароль для вашего аккаунта.</p>

        {!hasTokenParams ? <p className={styles.error}>Ссылка сброса некорректна</p> : null}

        <form className={styles.form} onSubmit={onSubmit}>
          <label htmlFor="password">Новый пароль</label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
            minLength={8}
          />

          <label htmlFor="confirmPassword">Повторите пароль</label>
          <input
            id="confirmPassword"
            type="password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
            required
            minLength={8}
          />

          {error ? <p className={styles.error}>{error}</p> : null}
          {message ? <p className={styles.success}>{message}</p> : null}

          <button type="submit" disabled={loading || !hasTokenParams}>
            {loading ? "Сохраняем..." : "Сохранить пароль"}
          </button>
        </form>

        <Link className={styles.backLink} href="/partner">
          Назад ко входу
        </Link>
      </div>
    </div>
  );
}
