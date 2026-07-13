"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode, useEffect, useMemo, useState } from "react";
import styles from "./layout.module.css";

const iconStatistics = "/statistics.svg";
const iconMyBusiness = "/mybusiness.svg";
const iconCategories = "/categories.svg";
const iconSpecialists = "/specialists.svg";
const iconSchedule = "/schedule.svg";
const iconManagers = "/managers.svg";
const iconReviews = "/otzyv.svg";
const iconProfile = "/profile.svg";
const iconSupport = "/support.svg";
const iconSettings = "/setting.svg";
const iconQuit = "/quit.svg";
const iconBell = "/notifications.svg";

type LayoutProps = { children: ReactNode };

type PartnerAuthUser = {
  company_name?: string;
  full_name?: string;
  username?: string;
  email?: string;
  user_type?: string;
};

type MenuItem = {
  label: string;
  icon: string;
  href?: string;
  match?: (pathname: string) => boolean;
};

const topMenu: MenuItem[] = [
  {
    label: "Статистика",
    icon: iconStatistics,
    href: "/partner/dashboard",
    match: (pathname) => pathname === "/partner/dashboard",
  },
  {
    label: "Мой бизнес",
    icon: iconMyBusiness,
    href: "/partner/dashboard/business",
    match: (pathname) => pathname.startsWith("/partner/dashboard/business"),
  },
  { label: "Услуги и категории", icon: iconCategories, href: "/partner/dashboard/manage" },
  { label: "Специалисты", icon: iconSpecialists, href: "/partner/dashboard/specialists" },
  {
    label: "Расписание и записи",
    icon: iconSchedule,
    href: "/partner/dashboard/schedule",
    match: (pathname) => pathname.startsWith("/partner/dashboard/schedule"),
  },
  { label: "Менеджеры", icon: iconManagers, href: "/partner/dashboard/managers" },
  { label: "Отзывы", icon: iconReviews },
];

const bottomMenu: MenuItem[] = [
  { label: "Личный кабинет", icon: iconProfile },
  { label: "Поддержка", icon: iconSupport },
  { label: "Настройки", icon: iconSettings },
];

function isItemActive(item: MenuItem, pathname: string) {
  if (item.match) return item.match(pathname);
  if (!item.href) return false;
  return pathname === item.href;
}

function MenuEntry({
  item,
  active,
  onClick,
}: {
  item: MenuItem;
  active?: boolean;
  onClick?: () => void;
}) {
  const className = `${styles.sideItem} ${active ? styles.sideItemActive : ""}`;

  if (item.href) {
    return (
      <Link href={item.href} className={className}>
        <img src={item.icon} alt="" className={styles.sideIcon} aria-hidden />
        <span>{item.label}</span>
      </Link>
    );
  }

  return (
    <button type="button" className={`${className} ${styles.disabledItem}`} onClick={onClick}>
      <img src={item.icon} alt="" className={styles.sideIcon} aria-hidden />
      <span>{item.label}</span>
    </button>
  );
}

export default function DashboardLayout({ children }: LayoutProps) {
  const pathname = usePathname();
  const router = useRouter();
  const [loadingLogout, setLoadingLogout] = useState(false);
  const [headerPartnerName, setHeaderPartnerName] = useState("Партнер");
  const [avatarLabel, setAvatarLabel] = useState("П");
  const [role, setRole] = useState<"partner" | "manager">("manager");
  const [authResolved, setAuthResolved] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const raw = localStorage.getItem("partner_auth_user");
    if (!raw) {
      setAuthResolved(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as PartnerAuthUser;
      const parsedRole = parsed.user_type === "manager" ? "manager" : "partner";
      setRole(parsedRole);
      const companyName = (parsed.company_name || "").trim();
      const fallbackName = (parsed.full_name || parsed.username || parsed.email || "").trim();
      const displayName = companyName || fallbackName || "Партнер";
      setHeaderPartnerName(displayName);

      const firstWord = displayName.split(/\s+/).find(Boolean) || "П";
      setAvatarLabel(firstWord.slice(0, 2).toUpperCase());
    } catch {
      // ignore invalid local storage payload
    } finally {
      setAuthResolved(true);
    }
  }, []);

  useEffect(() => {
    if (role !== "manager") {
      return;
    }
    const isBlocked =
      pathname === "/partner/dashboard" ||
      pathname === "/partner/dashboard/business" ||
      pathname.startsWith("/partner/dashboard/business/") ||
      pathname === "/partner/dashboard/managers" ||
      pathname.startsWith("/partner/dashboard/managers/");

    if (isBlocked) {
      router.replace("/partner/dashboard/manage");
    }
  }, [role, pathname, router]);

  const visibleTopMenu = useMemo(() => {
    if (!authResolved) {
      return topMenu.filter((item) => {
        const blockedLabels = new Set(["Статистика", "Мой бизнес", "Менеджеры"]);
        return !blockedLabels.has(item.label);
      });
    }

    if (role !== "manager") {
      return topMenu;
    }
    const blockedLabels = new Set(["Статистика", "Мой бизнес", "Менеджеры"]);
    return topMenu.filter((item) => !blockedLabels.has(item.label));
  }, [authResolved, role]);

  function handleLogout() {
    if (typeof window === "undefined") return;
    setLoadingLogout(true);
    localStorage.removeItem("partner_auth_user");
    localStorage.removeItem("partner_register_draft");
    router.push("/partner");
  }

  return (
    <div className={styles.screen}>
      <header className={styles.header}>
        <div className={styles.logoCell}>
          <img src="/logo.svg" alt="MySub" className={styles.logoImage} />
        </div>

        <div className={styles.headerMain}>
          <h1 className={styles.headerTitle}>{headerPartnerName}</h1>
          <p className={styles.headerSubtitle}>{!authResolved || role === "manager" ? "Менеджер" : "Партнёр"}</p>
        </div>

        <div className={styles.headerActions}>
          <button className={styles.notifyButton} type="button" aria-label="Уведомления">
            <img src={iconBell} alt="" />
          </button>
          <div className={styles.avatarPill}>{avatarLabel}</div>
        </div>
      </header>

      <aside className={styles.sidebar}>
        <div className={styles.menuTop}>
          {visibleTopMenu.map((item) => (
            <MenuEntry key={item.label} item={item} active={isItemActive(item, pathname)} />
          ))}
        </div>

        <div className={styles.menuBottom}>
          {bottomMenu.map((item) => (
            <MenuEntry key={item.label} item={item} />
          ))}
          <button type="button" className={styles.sideItem} onClick={handleLogout}>
            <img src={iconQuit} alt="" className={styles.sideIcon} aria-hidden />
            <span>{loadingLogout ? "Выход..." : "Выйти"}</span>
          </button>
        </div>
      </aside>

      <main className={styles.contentArea}>{children}</main>
    </div>
  );
}
