import type { components } from "../contract/api";
import { linkView, type Tone } from "../lib/status";
import { Badge } from "./ui/badge";

type DeviceStatus = components["schemas"]["DeviceStatus"];

const dot: Record<Tone, string> = {
  success: "bg-success",
  review: "bg-review",
  critical: "bg-critical",
  neutral: "bg-faint",
};

export function LinkPill({ status }: { status: DeviceStatus | null }) {
  const view = linkView(status);
  return (
    <Badge variant={view.tone}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${dot[view.tone]}`} />
      {view.label}
    </Badge>
  );
}
