import type { components } from "../contract/api";

type ReasonCode = components["schemas"]["ReasonCode"];
type MissingReason = components["schemas"]["MissingReason"];
type Source = components["schemas"]["Source"];
type LinkStatus = components["schemas"]["LinkStatus"];
type RiskLevel = components["schemas"]["RiskLevel"];
type Method = components["schemas"]["Method"];
type Severity = components["schemas"]["Severity"];
type PpgContact = components["schemas"]["PpgContact"];
export type MeasurementName = keyof components["schemas"]["Measurements"];

export const reasonCodeText: Record<ReasonCode, string> = {
  BASELINE_PENDING: "Aún no hay datos suficientes para conocer lo habitual de esta persona.",
  HR_ABOVE_PERSONAL_BASELINE:
    "La frecuencia cardíaca está por encima de lo habitual de esta persona.",
  HR_OUT_OF_RANGE: "La frecuencia cardíaca está fuera del rango esperado.",
  CONTACT_TEMPERATURE_OUT_OF_RANGE: "La temperatura de contacto está fuera del rango esperado.",
  FALL_PATTERN: "El movimiento coincide con el patrón de una posible caída.",
  PPG_CONTACT_LOST: "El sensor de pulso perdió contacto con la piel.",
};

export const ruleThresholdText: Record<ReasonCode, string> = {
  BASELINE_PENDING:
    "Hay menos de 120 lecturas válidas en la sesión. Hasta entonces la línea base es provisional y la regla de frecuencia sobre la base no se aplica.",
  HR_ABOVE_PERSONAL_BASELINE:
    "Cinco lecturas válidas seguidas con al menos 25 lpm sobre la línea base. La línea base es la mediana de las primeras 120 lecturas válidas de la sesión.",
  HR_OUT_OF_RANGE: "Una lectura válida por debajo de 40 lpm o por encima de 160 lpm.",
  CONTACT_TEMPERATURE_OUT_OF_RANGE:
    "Temperatura de contacto por debajo de 30,0 °C o por encima de 38,0 °C.",
  FALL_PATTERN:
    "Aceleración mínima bajo 3 m/s², luego aceleración máxima sobre 25 m/s² en la misma lectura o en la siguiente, y después dos lecturas con menos de 2 m/s² entre la máxima y la mínima.",
  PPG_CONTACT_LOST: "El sensor de pulso informa que no tiene contacto con la piel.",
};

export const missingReasonText: Record<MissingReason, string> = {
  no_contact: "El sensor no está en contacto con la piel.",
  warming_up: "El sensor todavía se está preparando.",
  sensor_error: "El sensor produjo una lectura no válida.",
  not_present: "Este sensor no está instalado en el dispositivo.",
};

export const sourceText: Record<Source, string> = {
  LIVE: "En vivo",
  REPLAY: "Repetición",
  HISTORICAL: "Histórico",
  SYNTHETIC: "Simulado",
};

export const linkStatusText: Record<LinkStatus, string> = {
  connected: "Conectado",
  stale: "Sin datos recientes",
  disconnected: "Desconectado",
};

export const replayPhaseText = {
  idle: "Sin repetición",
  playing: "Repetición en curso",
  ended: "Repetición terminada",
} as const;

export const staleBadgeText = "Dato anterior";

export function staleAgeText(minutes: number): string {
  return minutes < 1 ? "hace menos de 1 min" : `hace ${minutes} min`;
}

export const noReadingsText: Record<LinkStatus | "unknown", string> = {
  connected:
    "El enlace con el dispositivo está activo, pero todavía no llegó ninguna lectura. Los valores aparecen en cuanto el sensor empiece a medir.",
  stale: "El enlace no tiene datos recientes y todavía no llegó ninguna lectura.",
  disconnected: "El dispositivo está desconectado. Las lecturas aparecen cuando vuelva el enlace.",
  unknown: "Todavía no hay información del enlace ni lecturas del sensor.",
};

export const riskLevelText: Record<RiskLevel, string> = {
  normal: "Normal",
  review: "Para revisar",
  unavailable: "No disponible",
};

export const methodText: Record<Method, string> = {
  rules: "Análisis por reglas",
  ml: "Análisis por modelo",
};

export const severityText: Record<Severity, string> = {
  info: "Información",
  review: "Revisar",
  critical: "Crítico",
};

export const ppgContactText: Record<PpgContact, string> = {
  ok: "Contacto correcto",
  lost: "Sin contacto con la piel",
  unknown: "Contacto desconocido",
};

export const measurementText: Record<MeasurementName, string> = {
  heart_rate_bpm: "Frecuencia cardíaca",
  contact_temperature_c: "Temperatura de contacto",
  accel_min_m_s2: "Aceleración mínima",
  accel_max_m_s2: "Aceleración máxima",
  accel_mean_m_s2: "Aceleración media",
};

export const measurementUnit: Record<MeasurementName, string> = {
  heart_rate_bpm: "lpm",
  contact_temperature_c: "°C",
  accel_min_m_s2: "m/s²",
  accel_max_m_s2: "m/s²",
  accel_mean_m_s2: "m/s²",
};
