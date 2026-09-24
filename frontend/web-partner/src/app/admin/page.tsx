"use client";

import { Eye, EyeOff, LockKeyhole, UserRound } from "lucide-react";
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
    <main className={styles.page}>
      <section className={styles.panel}>
        <div className={styles.brand}><span className={styles.crown}>M</span> MySub</div>
        <div className={styles.formArea}>
          <p className={styles.eyebrow}>Административная панель</p>
          <h1>Вход для администратора</h1>
          <p className={styles.copy}>Используйте учётные данные администратора системы.</p>
          <form onSubmit={submit}>
            <label htmlFor="admin-login">Логин</label>
            <div className={styles.inputWrap}>
              <UserRound size={18} aria-hidden />
              <input id="admin-login" value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" required />
            </div>
            <label htmlFor="admin-password">Пароль</label>
            <div className={styles.inputWrap}>
              <LockKeyhole size={18} aria-hidden />
              <input id="admin-password" type={showPassword ? "text" : "password"} value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
              <button type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}>
                {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
              </button>
            </div>
            {error ? <p className={styles.error}>{error}</p> : null}
            <button className={styles.submit} disabled={loading} type="submit">{loading ? "Проверяем..." : "Войти"}</button>
          </form>
        </div>
      </section>
    </main>
  );
}