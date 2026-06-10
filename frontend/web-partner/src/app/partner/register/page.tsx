"use client";

import Image from "next/image";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

export default function PartnerRegisterPage() {
  const router = useRouter();
  const [acceptedOffer, setAcceptedOffer] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    router.push("/partner/register/credentials");
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
              <span className={styles.step}>2</span>
              <span className={styles.line} />
              <span className={styles.step}>3</span>
              <span className={styles.line} />
              <span className={styles.step}>4</span>
            </div>

            <form className={styles.card} onSubmit={onSubmit}>
              <h1 className={styles.title}>Договор оферты</h1>

          <section className={styles.offerBox}>
            <h2>ДОГОВОР ПУБЛИЧНОЙ ОФЕРТЫ</h2>
            <p>
              Настоящий документ является официальной офертой MySub на предоставление услуг
              платформы для управления бизнесом.
            </p>
            <p>
              1. Общие положения: Партнер получает доступ к платформе для управления услугами,
              записями клиентов и расписанием.
            </p>
            <p>
              2. Права и обязанности: Партнер обязуется предоставлять достоверную информацию и
              соблюдать правила платформы.
            </p>
            <p>
              3. Условия использования: Платформа предоставляется как есть. Партнер несет
              ответственность за сохранность своих данных доступа.
            </p>
            <p>
              4. Заключительные положения: Регистрируясь на платформе, партнер полностью
              принимает условия настоящего договора.
            </p>
              </section>

              <label className={styles.checkbox}>
                <input
                  type="checkbox"
                  checked={acceptedOffer}
                  onChange={(event) => setAcceptedOffer(event.target.checked)}
                />
                <span>
                  Я принимаю условия договора оферты и даю согласие на обработку персональных данных
                </span>
              </label>

              <div className={styles.actions}>
                <button className={`${styles.btn} ${styles.secondary}`} type="button" onClick={() => router.push("/partner")}> 
                  Отмена
                </button>
                <button className={`${styles.btn} ${styles.primary}`} type="submit" disabled={!acceptedOffer}>
                  Продолжить
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
