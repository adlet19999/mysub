"use client";

import Image from "next/image";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

export default function PartnerRegisterSuccessPage() {
  const router = useRouter();

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
              <span className={`${styles.step} ${styles.active}`}>4</span>
            </div>

            <section className={styles.card}>
              <h1 className={styles.title}>Регистрация завершена!</h1>

              <div className={styles.successIcon}>✓</div>

              <p className={styles.message}>Ваш аккаунт успешно создан!</p>
              <p className={styles.description}>Теперь вы можете войти в личный кабинет партнера</p>

              <button className={styles.btn} type="button" onClick={() => router.push("/partner")}>
                Перейти ко входу
              </button>
            </section>
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
