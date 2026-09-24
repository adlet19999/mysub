"use client";

import { Eye, EyeOff } from "lucide-react";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

export default function AdminLoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);
    try {
      const response = await fetch("/api/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const payload = (await response.json()) as { message?: string };
      if (!response.ok) {
        setError(payload.message || "Не удалось войти");
        return;
      }
      router.replace("/admin/dashboard");
    } catch {
      setError("Не удалось подключиться к серверу");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className={styles.shell}>
      <section className={styles.panel}>
        <div className={styles.left}>
          <header className={styles.brandRow}>
            <img src="/logo.svg" alt="MySub" width={118} height={42} />
          </header>
          <form className={styles.formWrap} onSubmit={submit}>
            <h1 className={styles.title}>Добро пожаловать в MySub</h1>
            <p className={styles.subtitle}>Введите логин и пароль для входа в административную панель</p>
            <label className={styles.label} htmlFor="admin-login">Логин</label>
            <input className={styles.input} id="admin-login" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" placeholder="Введите логин" required />
            <label className={styles.label} htmlFor="admin-password">Пароль</label>
            <div className={styles.passwordRow}>
              <input className={styles.input} id="admin-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" placeholder="••••••••" required />
              <button type="button" className={styles.eyeButton} onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}>
                {showPassword ? <EyeOff size={20} /> : <Eye size={20} />}
              </button>
            </div>
            {error ? <p className={styles.error}>{error}</p> : null}
            <button className={styles.loginButton} disabled={loading} type="submit">{loading ? "Проверяем..." : "Войти"}</button>
          </form>
          <footer className={styles.footer}>© 2026 MySub. Все права защищены</footer>
        </div>
        <div className={styles.right}><div className={styles.heroMedia} aria-hidden="true" /></div>
      </section>
    </main>
  );
}