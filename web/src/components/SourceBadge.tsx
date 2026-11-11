import type { components } from "../contract/api";
import { sourceText } from "../lib/copy";
import { Badge } from "./ui/badge";

type Source = components["schemas"]["Source"];

const variant: Record<Source, "success" | "accent" | "neutral"> = {
  LIVE: "success",
  REPLAY: "accent",
  SYNTHETIC: "accent",
  HISTORICAL: "neutral",
};

export function SourceBadge({ source }: { source: Source }) {
  return <Badge variant={variant[source]}>{sourceText[source]}</Badge>;
}
