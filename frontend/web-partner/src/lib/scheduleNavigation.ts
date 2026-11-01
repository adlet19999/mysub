const SCHEDULE = "/partner/dashboard/schedule";
export const ALL_SCHEDULE_SPECIALISTS = "__all_specialists__";

export function validScheduleDate(value: string | null) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime()) || `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}` !== value) return null;
  return date;
}

export function scheduleHref(date: string, specialist: string, booking?: number) {
  const params = new URLSearchParams({ date, specialist });
  if (booking) params.set("booking", String(booking));
  return `${SCHEDULE}?${params}`;
}

export function scheduleReturnHref(search: string) {
  const value = new URLSearchParams(search).get("return_to");
  if (!value || !(value === SCHEDULE || value.startsWith(`${SCHEDULE}?`))) return SCHEDULE;
  const url = new URL(value, "https://schedule.local");
  return url.origin === "https://schedule.local" && url.pathname === SCHEDULE ? `${url.pathname}${url.search}` : SCHEDULE;
}

export function calendarBookingVisible(status: string) {
  return !["cancelled", "canceled", "отменен", "отменён", "отменена", "no_show", "no-show", "missed", "неявка"].includes(status.trim().toLowerCase());
}
