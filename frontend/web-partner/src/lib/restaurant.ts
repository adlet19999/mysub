export type RestaurantReservation = {
  table_id: number;
  table_name: string;
  table_capacity: number;
  party_size: number;
  ends_at: string;
  arrived_at: string | null;
  completed_at: string | null;
  paid_amount: string | null;
  notice: string;
  segments: { starts_at: string; ends_at: string; is_extension: boolean }[];
};

export type BusinessTable = { id: number; name: string; capacity: number; description: string; is_active: boolean };

export function restaurantCalendarSegments(segments: RestaurantReservation["segments"]): RestaurantReservation["segments"] {
  return segments.flatMap((segment) => {
    const offset = segment.starts_at.match(/(?:Z|[+-]\d{2}:\d{2})$/)?.[0];
    const startsAt = Date.parse(segment.starts_at);
    const endsAt = Date.parse(segment.ends_at);
    if (!offset || !Number.isFinite(startsAt) || !Number.isFinite(endsAt) || endsAt <= startsAt) {
      throw new Error("Некорректное время ресторанной брони.");
    }
    const offsetMinutes = offset === "Z" ? 0 : (Number(offset.slice(1, 3)) * 60 + Number(offset.slice(4, 6))) * (offset[0] === "-" ? -1 : 1);
    const format = (timestamp: number) => new Date(timestamp + offsetMinutes * 60_000).toISOString().slice(0, -1) + offset;
    const result: RestaurantReservation["segments"] = [];
    let cursor = startsAt;
    while (cursor < endsAt) {
      const midnight = Date.parse(`${format(cursor).slice(0, 10)}T00:00:00${offset}`) + 86_400_000;
      const fragmentEnd = Math.min(midnight, endsAt);
      result.push({
        ...segment,
        starts_at: cursor === startsAt ? segment.starts_at : format(cursor),
        ends_at: fragmentEnd === endsAt ? segment.ends_at : format(fragmentEnd),
      });
      cursor = fragmentEnd;
    }
    return result;
  });
}
