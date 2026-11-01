export type RecurringVisit = { date: string; time: string; timeOverride?: boolean };

export function applyDefaultVisitTime(visits: RecurringVisit[], time: string) {
  if (!time) return visits;
  return visits.map((visit) => visit.timeOverride ? visit : { ...visit, time });
}

export function changeVisitTime(visits: RecurringVisit[], index: number, time: string) {
  const common = index === 0 || visits.every((visit) => !visit.time);
  if (!common && visits[index]?.time === time) return visits;
  const next = time && common ? applyDefaultVisitTime(visits, time) : visits;
  return next.map((visit, current) => current === index ? { ...visit, time, timeOverride: !common && Boolean(time) } : visit);
}
