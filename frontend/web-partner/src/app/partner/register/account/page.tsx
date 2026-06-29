"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "../page.module.css";

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
      <path d="M3 3L21 21" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
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

type RegisterDraft = {
  full_name?: string;
  phone?: string;
  email?: string;
  company_name?: string;
  business_category?: string;
  address?: string;
};

export default function PartnerRegisterAccountPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [draft, setDraft] = useState<RegisterDraft>({});

  useEffect(() => {
    if (typeof window === "undefined") return;
    const raw = localStorage.getItem("partner_register_draft");
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as RegisterDraft;
      setDraft(parsed);
      if (parsed.email) {
        setEmail(parsed.email);
      }
    } catch {
      localStorage.removeItem("partner_register_draft");
    }
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Пароли не совпадают");
      return;
    }

    setLoading(true);

    try {
      const response = await fetch("/api/partner/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          login: email,
          password,
          acceptedOffer: true,
          full_name: (draft.full_name || "").trim() || email,
          phone: (draft.phone || "").trim() || "+7",
          company_name: (draft.company_name || "").trim(),
          business_category: (draft.business_category || "").trim(),
          address: (draft.address || "").trim(),
        }),
      });

      const payload = (await response.json()) as { message?: string };
      if (!response.ok) {
        setError(payload.message || "Не удалось завершить регистрацию");
        return;
      }

      if (typeof window !== "undefined") {
        localStorage.removeItem("partner_register_draft");
      }
      router.push("/partner/register/success");
    } catch {
      setError("Не удалось подключиться к серверу");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.shell}>
      <div className={styles.panel}>
        <div className={styles.page}>
          <main className={styles.container}>
            <header className={styles.header}>
              <Image src="/logo.svg" alt="MySub" width={132} height={46} priority />
              <p className={styles.subtitle}>Регистрация нового партнера</p>
            </header>

            <div className={styles.steps}>
              <span className={`${styles.step} ${styles.active}`}>1</span>
              <span className={styles.line} />
              <span className={`${styles.step} ${styles.active}`}>2</span>
              <span className={styles.line} />
              <span className={`${styles.step} ${styles.active}`}>3</span>
              <span className={styles.line} />
              <span className={styles.step}>4</span>
            </div>

            <form className={styles.card} onSubmit={onSubmit}>
              <h1 className={styles.title}>Создание аккаунта</h1>

              <label className={styles.label} htmlFor="register-login">
                Email для входа *
              </label>
              <input
                id="register-login"
                className={styles.input}
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder=""
              />

              <label className={styles.label} htmlFor="register-password">
                Пароль *
              </label>
              <div className={styles.passwordRow}>
                <input
                  id="register-password"
                  className={`${styles.input} ${styles.inputWithIcon}`}
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder=""
                />
                <button
                  type="button"
                  className={styles.eyeButton}
                  onClick={() => setShowPassword((value) => !value)}
                  aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                >
                  {showPassword ? <EyeClosedIcon /> : <EyeOpenIcon />}
                </button>
              </div>

              <label className={styles.label} htmlFor="register-confirm-password">
                Подтверждение пароля *
              </label>
              <div className={styles.passwordRow}>
                <input
                  id="register-confirm-password"
                  className={`${styles.input} ${styles.inputWithIcon}`}
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(event) => setConfirmPassword(event.target.value)}
                  placeholder=""
                />
                <button
                  type="button"
                  className={styles.eyeButton}
                  onClick={() => setShowConfirmPassword((value) => !value)}
                  aria-label={showConfirmPassword ? "Скрыть пароль" : "Показать пароль"}
                >
                  {showConfirmPassword ? <EyeClosedIcon /> : <EyeOpenIcon />}
                </button>
              </div>

              {error ? <p className={styles.error}>{error}</p> : null}

              <div className={styles.actions}>
                <button
                  className={`${styles.btn} ${styles.secondary}`}
                  type="button"
                  onClick={() => router.push("/partner/register/credentials")}
                >
                  Назад
                </button>
                <button className={`${styles.btn} ${styles.primary}`} type="submit" disabled={loading}>
                  {loading ? "Сохраняем..." : "Зарегистрироваться"}
                </button>
              </div>

              <p className={styles.loginLink}>
                Уже есть аккаунт?{" "}
                <button type="button" onClick={() => router.push("/partner")}>
                  Войти
                </button>
              </p>
            </form>
          </main>

          <footer className={styles.footer}>
            <span>© 2026 MySub. Все права защищены</span>
            <div className={styles.footerLinks}>
              <button type="button">Политика конфиденциальности</button>
              <button type="button">Публичная оферта</button>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
