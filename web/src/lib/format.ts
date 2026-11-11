const timeFormat = new Intl.DateTimeFormat("es", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

const dateTimeFormat = new Intl.DateTimeFormat("es", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatTime(iso: string | null): string {
  if (!iso) return "Sin registro";
  const t = Date.parse(iso);
  return Number.isNaN(t) ? "Sin registro" : timeFormat.format(t);
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "Sin registro";
  const t = Date.parse(iso);
  return Number.isNaN(t) ? "Sin registro" : dateTimeFormat.format(t);
}

export function formatValue(value: number | null, digits = 0): string {
  if (value === null) return "Sin dato";
  return value.toFixed(digits);
}
