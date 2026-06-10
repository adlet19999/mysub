"use client";

import Image from "next/image";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "../page.module.css";

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
              <input
                id="register-password"
                className={styles.input}
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder=""
              />

              <label className={styles.label} htmlFor="register-confirm-password">
                Подтверждение пароля *
              </label>
              <input
                id="register-confirm-password"
                className={styles.input}
                type="password"
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
                placeholder=""
              />

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
