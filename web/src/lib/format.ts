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

export function formatDuration(startIso: string, endIso: string | null): string {
  if (!endIso) return "En curso";
  const seconds = Math.round((Date.parse(endIso) - Date.parse(startIso)) / 1000);
  if (Number.isNaN(seconds)) return "Sin registro";
  const minutes = Math.floor(seconds / 60);
  return minutes > 0 ? `${minutes} min ${seconds % 60} s` : `${seconds} s`;
}

export function formatClock(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

export function formatValue(value: number | null, digits = 0): string {
  if (value === null) return "Sin dato";
  return value.toFixed(digits);
}
