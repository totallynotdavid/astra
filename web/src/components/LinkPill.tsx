import type { components } from "../contract/api";
import { linkView, replayView, type ReplayPhase, type Tone } from "../lib/status";
import { Badge } from "./ui/badge";

type DeviceStatus = components["schemas"]["DeviceStatus"];

const dot: Record<Tone, string> = {
  success: "bg-success",
  review: "bg-review",
  critical: "bg-critical",
  neutral: "bg-faint",
  accent: "bg-accent",
};

export function LinkPill({
  status,
  replay = null,
}: {
  status: DeviceStatus | null;
  replay?: ReplayPhase | null;
}) {
  const view = replay ? replayView(replay) : linkView(status);
  return (
    <Badge variant={view.tone}>
      <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${dot[view.tone]}`} />
      {view.label}
    </Badge>
  );
}
