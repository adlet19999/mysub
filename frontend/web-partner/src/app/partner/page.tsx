"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import styles from "./page.module.css";

function EyeOpenIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M2.46 12C3.73 7.94 7.52 5 12 5C16.48 5 20.27 7.94 21.54 12C20.27 16.06 16.48 19 12 19C7.52 19 3.73 16.06 2.46 12Z"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.7" />
    </svg>
  );
}

function EyeClosedIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M3 3L21 21"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M9.88 9.88C9.34 10.42 9 11.17 9 12C9 13.66 10.34 15 12 15C12.83 15 13.58 14.66 14.12 14.12"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M6.79 6.79C5.01 8.05 3.65 9.87 2.87 12C4.14 16.06 7.92 19 12.41 19C14.24 19 15.95 18.5 17.42 17.63"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M10.74 5.08C11.15 5.03 11.57 5 12 5C16.48 5 20.27 7.94 21.54 12C21.12 13.34 20.42 14.55 19.53 15.56"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function PartnerPage() {
  const router = useRouter();
  const [login, setLogin] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch("/api/partner/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ login, password }),
      });

      const payload = (await response.json()) as {
        message?: string;
        user?: {
          id: number;
          username: string;
          email: string;
          phone?: string;
          user_type?: string;
          company_name?: string;
          business_category?: string;
          address?: string;
        };
      };
      if (!response.ok) {
        setError(payload.message || "Ошибка авторизации");
        return;
      }

      if (payload.user && typeof window !== "undefined") {
        localStorage.setItem("partner_auth_user", JSON.stringify(payload.user));
      }
      if (payload.user?.user_type === "manager") {
        router.push("/partner/dashboard/manage");
      } else {
        router.push("/partner/dashboard");
      }
    } catch {
      setError("Не удалось подключиться к серверу");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.shell}>
      <div className={styles.panel}>
        <section className={styles.left}>
          <header className={styles.brandRow}>
            <Image src="/logo.svg" alt="MySub" width={118} height={42} priority />
          </header>

          <form className={styles.formWrap} onSubmit={onSubmit}>
            <h1 className={styles.title}>Добро пожаловать в MySub</h1>
            <p className={styles.subtitle}>Введите логин и пароль для входа в кабинет партнера</p>

            <label className={styles.label} htmlFor="login">
              Логин
            </label>
            <input
              id="login"
              type="text"
              placeholder="Введите логин"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              className={styles.input}
            />

            <label className={styles.label} htmlFor="password">
              Пароль
            </label>
            <div className={styles.passwordRow}>
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={styles.input}
              />
              <button
                type="button"
                className={styles.eyeButton}
                onClick={() => setShowPassword((v) => !v)}
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
              >
                {showPassword ? <EyeClosedIcon /> : <EyeOpenIcon />}
              </button>
            </div>

            {error ? <p className={styles.error}>{error}</p> : null}

            <button className={styles.loginButton} type="submit" disabled={loading}>
              {loading ? "Входим..." : "Войти"}
            </button>

            <button
              className={styles.linkButton}
              type="button"
              onClick={() => router.push("/partner/forgot-password")}
            >
              Забыли пароль?
            </button>

            <button className={styles.linkButton} type="button" onClick={() => router.push("/partner/register")}>
              Регистрация нового партнера
            </button>
          </form>

          <footer className={styles.footer}>
            <span>© 2026 MySub. Все права защищены</span>
            <div className={styles.footerLinks}>
              <button type="button">Политика конфиденциальности</button>
              <button type="button">Публичная оферта</button>
            </div>
          </footer>
        </section>

        <section className={styles.right}>
          <div className={styles.heroMedia}>
            <Image
              src="/partner-login-left.webp"
              alt="MySub partner preview"
              fill
              sizes="(max-width: 1080px) 100vw, 54vw"
              className={styles.heroImage}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
