"use client";

import { FormEvent, Suspense, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Eye, EyeOff } from "lucide-react";
import styles from "./page.module.css";

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}

function ResetPasswordForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const uid = (searchParams.get("uid") || "").trim();
  const token = (searchParams.get("token") || "").trim();
  const email = (searchParams.get("email") || "").trim();
  const isInitialPasswordChange = searchParams.get("initial") === "true";
  const hasTokenParams = useMemo(
    () => (isInitialPasswordChange ? Boolean(email) : Boolean(uid && token)),
    [email, isInitialPasswordChange, token, uid],
  );

  const [currentPassword, setCurrentPassword] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
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
        body: JSON.stringify(
          isInitialPasswordChange
            ? { email, currentPassword, newPassword: password }
            : { uid, token, newPassword: password },
        ),
      });

      const payload = (await response.json()) as { message?: string };
      if (!response.ok) {
        setError(payload.message || "Не удалось обновить пароль");
        return;
      }

      setMessage(payload.message || "Пароль обновлен");
      setTimeout(() => router.push(isInitialPasswordChange ? "/partner/dashboard/manage" : "/partner"), 1200);
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
        <p className={styles.subtitle}>
          {isInitialPasswordChange ? "Для продолжения замените временный пароль." : "Задайте новый пароль для вашего аккаунта."}
        </p>

        {!hasTokenParams ? <p className={styles.error}>Ссылка сброса некорректна</p> : null}

        <form className={styles.form} onSubmit={onSubmit}>
          {isInitialPasswordChange ? (
            <>
              <label htmlFor="currentPassword">Текущий пароль</label>
              <input
                id="currentPassword"
                type="password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
                required
              />
            </>
          ) : null}
          <label htmlFor="password">Новый пароль</label>
          <div className={styles.passwordField}>
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
              minLength={8}
            />
            <button
              className={styles.eyeButton}
              type="button"
              onClick={() => setShowPassword((value) => !value)}
              aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              title={showPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
            </button>
          </div>

          <label htmlFor="confirmPassword">Повторите пароль</label>
          <div className={styles.passwordField}>
            <input
              id="confirmPassword"
              type={showConfirmPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(event) => setConfirmPassword(event.target.value)}
              required
              minLength={8}
            />
            <button
              className={styles.eyeButton}
              type="button"
              onClick={() => setShowConfirmPassword((value) => !value)}
              aria-label={showConfirmPassword ? "Скрыть пароль" : "Показать пароль"}
              title={showConfirmPassword ? "Скрыть пароль" : "Показать пароль"}
            >
              {showConfirmPassword ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
            </button>
          </div>

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
