import type { components } from "../contract/api";

type Alert = components["schemas"]["Alert"];
type AlertPriority = components["schemas"]["AlertPriority"];

export const priorityRank: Record<AlertPriority, number> = {
  high: 3,
  medium: 2,
  low: 1,
};

export function pendingAlerts(alerts: Alert[], memberId: string): Alert[] {
  return alerts.filter((alert) => alert.crew_member_id === memberId && alert.status !== "resolved");
}

export function highestPriority(alerts: Alert[]): AlertPriority | null {
  let top: AlertPriority | null = null;
  for (const alert of alerts) {
    if (!top || priorityRank[alert.priority] > priorityRank[top]) top = alert.priority;
  }
  return top;
}
