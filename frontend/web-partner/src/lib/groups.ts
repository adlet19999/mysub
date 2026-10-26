export type GroupParticipant = {
  id: number;
  client_name: string;
  client_phone: string;
  status: string;
  starts_at: string;
  base_price: string;
  final_price: string;
  session_id: number | null;
  original_session_id: number | null;
  is_moved: boolean;
  is_individual_override: boolean;
};

export type GroupSession = {
  id: number;
  group_id: number;
  group_name: string;
  service_id: number;
  service_name: string;
  specialist_id: number;
  specialist_name: string;
  starts_at: string;
  status: "scheduled" | "cancelled";
  original_starts_at: string | null;
  capacity: number;
  occupied_places: number;
  available_places: number;
  duration_minutes: number;
  base_price: string;
  participants: GroupParticipant[];
};

export type BookingGroup = {
  id: number;
  name: string;
  service_id: number;
  service_name: string;
  specialist_id: number;
  specialist_name: string;
  capacity: number;
  duration_minutes: number;
  price: string;
  price_mode: "per_visit" | "total";
  session_count: number;
  future_session_count: number;
  next_session: string | null;
  participant_count: number;
};

export type GroupDetail = BookingGroup & {
  sessions: GroupSession[];
  bookings: GroupParticipant[];
};

export function isActiveVisit(status: string) {
  return ["booked", "pending", "записан", "записана"].includes(status.toLowerCase());
}

export function groupBookingStatus(participants: { status: string }[]) {
  const current = participants.filter((item) => !["cancelled", "canceled", "отменен", "отменена"].includes(item.status.toLowerCase()));
  if (!current.length || current.some((item) => isActiveVisit(item.status))) return "booked";
  if (current.some((item) => ["completed", "done", "завершен", "завершена"].includes(item.status.toLowerCase()))) return "completed";
  return "no_show";
}

export function lessonCount(count: number) {
  const lastTwo = count % 100;
  const word = lastTwo >= 11 && lastTwo <= 14 ? "занятий" : count % 10 === 1 ? "занятие" : count % 10 >= 2 && count % 10 <= 4 ? "занятия" : "занятий";
  return `${count} ${word}`;
}

export function enrollmentTotal(sessions: GroupSession[], selectedIds: number[]) {
  return sessions.filter((session) => selectedIds.includes(session.id))
    .reduce((cents, session) => cents + Math.round(Number(session.base_price) * 100), 0) / 100;
}

export function selectableSessions(sessions: GroupSession[], now: number) {
  return sessions.filter((session) => session.status === "scheduled" && new Date(session.starts_at).getTime() > now && session.available_places > 0);
}
