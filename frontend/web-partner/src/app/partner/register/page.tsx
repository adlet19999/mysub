"use client";

import Image from "next/image";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import styles from "./page.module.css";

const OFFER_PARAGRAPHS = [
  "Настоящий документ является официальной офертой MySub на предоставление услуг платформы для управления бизнесом и клиентскими записями.",
  "1. Предмет договора. Партнер получает доступ к программному обеспечению и сервисам MySub для публикации услуг, ведения расписания, управления заявками и аналитикой.",
  "2. Права и обязанности партнера. Партнер обязуется предоставлять достоверные данные о компании, корректно описывать услуги и соблюдать действующее законодательство.",
  "3. Права и обязанности платформы. Платформа обеспечивает доступ к функционалу в режиме 24/7, за исключением технических работ, аварийных обновлений и форс-мажорных обстоятельств.",
  "4. Персональные данные. Партнер подтверждает, что имеет правовые основания на обработку данных сотрудников и клиентов, передаваемых через платформу.",
  "5. Финансовые условия. Стоимость услуг, комиссии и иные условия тарификации определяются действующим тарифным планом, опубликованным в личном кабинете.",
  "6. Ограничение ответственности. Платформа не несет ответственность за недоступность сервиса, вызванную проблемами связи, действиями провайдеров, DDoS-атаками или иными внешними факторами.",
  "7. Интеллектуальная собственность. Все права на программный код, интерфейс и товарные знаки MySub принадлежат правообладателю и защищены применимым законодательством.",
  "8. Расторжение договора. Партнер вправе прекратить использование платформы в любое время. Платформа вправе ограничить доступ при нарушении правил сервиса.",
  "9. Коммуникации. Партнер соглашается получать сервисные уведомления на указанный email и номер телефона, включая сообщения о статусах заявок и обновлениях.",
  "10. Заключительные положения. Продолжая регистрацию и используя платформу, партнер подтверждает полное и безусловное согласие с условиями настоящей оферты.",
  "11. Применимое право. Все спорные вопросы решаются путем переговоров, а при недостижении согласия — в порядке, установленном действующим законодательством.",
  "12. Редакции документа. Платформа вправе вносить изменения в условия оферты, размещая актуальную редакцию в интерфейсе. Продолжение использования означает принятие изменений.",
];

export default function PartnerRegisterPage() {
  const router = useRouter();
  const [acceptedOffer, setAcceptedOffer] = useState(false);
  const [isOfferRead, setIsOfferRead] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    router.push("/partner/register/credentials");
  }

  function handleOfferScroll(event: React.UIEvent<HTMLElement>) {
    if (isOfferRead) {
      return;
    }
    const element = event.currentTarget;
    const scrolledToBottom = element.scrollTop + element.clientHeight >= element.scrollHeight - 4;
    if (scrolledToBottom) {
      setIsOfferRead(true);
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
              <span className={styles.step}>2</span>
              <span className={styles.line} />
              <span className={styles.step}>3</span>
              <span className={styles.line} />
              <span className={styles.step}>4</span>
            </div>

            <form className={styles.card} onSubmit={onSubmit}>
              <h1 className={styles.title}>Договор оферты</h1>

          <section className={styles.offerBox} onScroll={handleOfferScroll}>
            <h2>ДОГОВОР ПУБЛИЧНОЙ ОФЕРТЫ</h2>
            {OFFER_PARAGRAPHS.map((paragraph, index) => (
              <p key={index}>{paragraph}</p>
            ))}
              </section>

              {!isOfferRead ? (
                <p className={styles.offerScrollHint}>Прокрутите текст оферты до конца, чтобы подтвердить ознакомление.</p>
              ) : (
                <label className={styles.checkbox}>
                  <input
                    type="checkbox"
                    checked={acceptedOffer}
                    onChange={(event) => setAcceptedOffer(event.target.checked)}
                  />
                  <span>С условиями оферты ознакомлен(а), принимаю их и даю согласие на обработку персональных данных.</span>
                </label>
              )}

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
