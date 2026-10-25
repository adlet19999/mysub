export function toggleCalendarDate(selected: string[], dateKey: string): string[] {
  return selected.includes(dateKey)
    ? selected.filter((key) => key !== dateKey)
    : [...selected, dateKey];
}

export function selectCalendarArea(keys: string[], anchor: number, end: number, original: string[], additive: boolean): string[] {
  const firstRow = Math.min(Math.floor(anchor / 7), Math.floor(end / 7));
  const lastRow = Math.max(Math.floor(anchor / 7), Math.floor(end / 7));
  const firstColumn = Math.min(anchor % 7, end % 7);
  const lastColumn = Math.max(anchor % 7, end % 7);
  const selected = new Set(additive ? original : []);
  for (let row = firstRow; row <= lastRow; row += 1) {
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      const key = keys[row * 7 + column];
      if (key) selected.add(key);
    }
  }
  return [...selected].sort();
}
