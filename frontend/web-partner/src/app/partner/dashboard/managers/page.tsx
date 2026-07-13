"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import styles from "./page.module.css";

type Manager = {
  id: number;
  full_name: string;
  phone: string;
  email: string;
  service_kind_ids: number[];
  is_active: boolean;
};

type FormState = {
  fullName: string;
  phone: string;
  email: string;
  password: string;
  role: string;
  resetPasswordOnFirstLogin: boolean;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.trim() || "/api/v1";
const TENANT_DEFAULT = process.env.NEXT_PUBLIC_TENANT_SLUG ?? "public";

export default function ManagersPage() {
  const tenant = TENANT_DEFAULT;

  const [partnerEmail, setPartnerEmail] = useState("");
  const [authResolved, setAuthResolved] = useState(false);
  const [managers, setManagers] = useState<Manager[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editingManagerId, setEditingManagerId] = useState<number | null>(null);
  const [form, setForm] = useState<FormState>({
    fullName: "",
    phone: "",
    email: "",
    password: "",
    role: "Менеджер",
    resetPasswordOnFirstLogin: true,
  });

  const [toastText, setToastText] = useState("");
  const [formError, setFormError] = useState("");

  const visibleManagers = useMemo(() => {
    const text = searchQuery.trim().toLowerCase();
    if (!text) {
      return managers;
    }
    return managers.filter((item) => {
      return (
        item.full_name.toLowerCase().includes(text) ||
        item.phone.toLowerCase().includes(text) ||
        item.email.toLowerCase().includes(text)
      );
    });
  }, [managers, searchQuery]);

  async function api(path: string, init?: RequestInit) {
    return fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        "X-Tenant": tenant,
        ...(partnerEmail ? { "X-Partner-Email": partnerEmail } : {}),
        ...(init?.headers ?? {}),
      },
    });
  }

  async function loadData() {
    if (!partnerEmail) {
      return;
    }
    try {
      const response = await api("/partner/managers/");
      if (!response.ok) {
        return;
      }
      const payload = (await response.json()) as Manager[];
      setManagers(Array.isArray(payload) ? payload : []);
    } catch {
      // silent fail for dashboard resilience
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) {
      return;
    }
    try {
      const parsed = JSON.parse(raw) as { email?: string; username?: string };
      const email = (parsed.email || parsed.username || "").trim().toLowerCase();
      if (email) {
        setPartnerEmail(email);
      }
    } catch {
      // ignore corrupted payload
    } finally {
      setAuthResolved(true);
    }
  }, []);

  useEffect(() => {
    if (!authResolved) {
      return;
    }
    void loadData();
  }, [authResolved, partnerEmail]);

  function openCreateModal() {
    setIsEditing(false);
    setEditingManagerId(null);
    setFormError("");
    setForm({
      fullName: "",
      phone: "",
      email: "",
      password: "",
      role: "Менеджер",
      resetPasswordOnFirstLogin: true,
    });
    setIsModalOpen(true);
  }

  function openEditModal(item: Manager) {
    setIsEditing(true);
    setEditingManagerId(item.id);
    setFormError("");
    setForm({
      fullName: item.full_name,
      phone: item.phone,
      email: item.email,
      password: "",
      role: "Менеджер",
      resetPasswordOnFirstLogin: true,
    });
    setIsModalOpen(true);
  }

  async function submitManager(event: FormEvent) {
    event.preventDefault();
    setFormError("");

    if (!form.fullName.trim() || !form.phone.trim() || !form.email.trim()) {
      setFormError("Заполните обязательные поля");
      return;
    }

    if (!isEditing && !form.password.trim()) {
      setFormError("Для менеджера нужно задать пароль");
      return;
    }

    const response = await api(
      isEditing && editingManagerId ? `/partner/managers/${editingManagerId}/` : "/partner/managers/",
      {
        method: isEditing && editingManagerId ? "PATCH" : "POST",
        body: JSON.stringify({
          full_name: form.fullName,
          phone: form.phone,
          email: form.email,
          ...(isEditing ? {} : { password: form.password }),
          service_kind_ids: [],
          is_active: true,
        }),
      },
    );

    if (!response.ok) {
      try {
        const payload = (await response.json()) as { message?: string };
        setFormError(payload.message || "Не удалось сохранить менеджера");
      } catch {
        setFormError("Не удалось сохранить менеджера");
      }
      return;
    }

    setIsModalOpen(false);
    await loadData();
    setToastText(isEditing ? "Данные менеджера обновлены" : "Новый менеджер добавлен в список");
    setTimeout(() => setToastText(""), 2600);
  }

  async function toggleStatus(manager: Manager) {
    const response = await api(`/partner/managers/${manager.id}/`, {
      method: "PATCH",
      body: JSON.stringify({ is_active: !manager.is_active }),
    });
    if (!response.ok) {
      return;
    }
    await loadData();
  }

  return (
    <>
      <main className={styles.page}>
        <section className={styles.block}>
          {toastText ? (
            <div className={styles.toast}>
              <div>
                <strong>{toastText}</strong>
                <div>Изменения успешно применены</div>
              </div>
              <button type="button" onClick={() => setToastText("")}>×</button>
            </div>
          ) : null}

          <header className={styles.head}>
            <div>
              <h1>Менеджеры</h1>
              <p>Управление командой</p>
            </div>
            <button type="button" className={styles.addButton} onClick={openCreateModal} disabled={!partnerEmail}>
              <span>+</span>
              Добавить менеджера
            </button>
          </header>

          <div className={styles.searchWrap}>
            <img src="/search.svg" alt="" className={styles.searchIconImage} aria-hidden />
            <input
              className={styles.search}
              placeholder="Поиск по ФИО, телефону и email"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
            />
          </div>

          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>ФИО</th>
                  <th>Телефон</th>
                  <th>Email</th>
                  <th>Роль</th>
                  <th>Статус</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                {visibleManagers.map((manager) => (
                  <tr key={manager.id}>
                    <td>{manager.full_name}</td>
                    <td>{manager.phone}</td>
                    <td>{manager.email}</td>
                    <td>Менеджер</td>
                    <td>
                      <span className={manager.is_active ? styles.statusActive : styles.statusBlocked}>
                        {manager.is_active ? "Активен" : "Заблокирован"}
                      </span>
                    </td>
                    <td>
                      <div className={styles.actions}>
                        <button type="button" onClick={() => openEditModal(manager)} title="Редактировать">
                          <img src="/change.svg" alt="" className={styles.actionIcon} aria-hidden />
                        </button>
                        <button
                          type="button"
                          onClick={() => void toggleStatus(manager)}
                          title={manager.is_active ? "Архивировать" : "Разархивировать"}
                        >
                          <img src="/Archieve.svg" alt="" className={styles.actionIcon} aria-hidden />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {!visibleManagers.length ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>👥</div>
              <h3>Менеджеров пока нет !</h3>
              <p>Чтобы включить нового менеджера, выберите опцию “Добавить менеджера”</p>
            </div>
          ) : null}

          {authResolved && !partnerEmail ? (
            <p className={styles.error}>Не удалось определить текущего партнера. Выйдите и войдите снова.</p>
          ) : null}
        </section>
      </main>

      {isModalOpen ? (
        <div className={styles.overlay}>
          <form className={styles.modal} onSubmit={submitManager}>
            <header className={styles.modalHeader}>
              <div className={styles.modalTitleWrap}>
                <img src="/modal_icon.svg" alt="" className={styles.modalIcon} aria-hidden />
                <h2>{isEditing ? "Редактировать менеджера" : "Добавить менеджера"}</h2>
              </div>
              <button type="button" className={styles.close} onClick={() => setIsModalOpen(false)}>
                ×
              </button>
            </header>

            <div className={styles.modalBody}>
              <label>
                ФИО *
                <input
                  value={form.fullName}
                  onChange={(event) => setForm((prev) => ({ ...prev, fullName: event.target.value }))}
                  placeholder="Курманова Альмира Армановна"
                  required
                />
              </label>

              <label>
                Телефон *
                <input
                  value={form.phone}
                  onChange={(event) => setForm((prev) => ({ ...prev, phone: event.target.value }))}
                  placeholder="+7 (747) 123-45-67"
                  required
                />
              </label>

              <label>
                Email *
                <input
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm((prev) => ({ ...prev, email: event.target.value }))}
                  placeholder="manager@example.com"
                  required
                />
              </label>

              {!isEditing ? (
                <label>
                  Пароль *
                  <input
                    type="password"
                    value={form.password}
                    onChange={(event) => setForm((prev) => ({ ...prev, password: event.target.value }))}
                    placeholder="Минимум 8 символов"
                    required
                    minLength={8}
                  />
                </label>
              ) : null}

              <label>
                Роль *
                <input value={form.role} readOnly />
              </label>

              <label className={styles.checkRow}>
                <input
                  type="checkbox"
                  checked={form.resetPasswordOnFirstLogin}
                  onChange={(event) => setForm((prev) => ({ ...prev, resetPasswordOnFirstLogin: event.target.checked }))}
                />
                При первом входе изменить пароль
              </label>

              {formError ? <p className={styles.error}>{formError}</p> : null}
            </div>

            <footer className={styles.modalFooter}>
              <button type="button" className={styles.cancelButton} onClick={() => setIsModalOpen(false)}>
                Отменить
              </button>
              <button type="submit" className={styles.saveButton}>{isEditing ? "Сохранить" : "Создать"}</button>
            </footer>
          </form>
        </div>
      ) : null}
    </>
  );
}
