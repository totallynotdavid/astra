import type { components } from "../contract/api";
import { GROUP_LANE, type Timeline } from "../data/runs";
import { findingLabelText } from "../lib/copy";
import { formatClock, formatList } from "../lib/format";

type FindingLabel = components["schemas"]["FindingLabel"];

const barTone: Partial<Record<FindingLabel, string>> = {
  possible_fall: "bg-critical",
  explicit_distress_phrase: "bg-critical",
  abrupt_movement: "bg-review",
  frequent_interruptions: "bg-review",
  prolonged_inactivity: "bg-neutral-10",
  long_silence: "bg-neutral-10",
  isolation: "bg-success",
  interaction: "bg-accent",
};

const columns = "grid grid-cols-[10rem_1fr] items-center gap-x-3";

function tickAlign(tick: number, duration: number): string {
  if (tick === 0) return "";
  return tick === duration ? "-translate-x-full" : "-translate-x-1/2";
}

export function laneTitle(lane: Timeline["lanes"][number]): string {
  if (lane.member) return `${lane.member.code} · ${lane.member.display_name}`;
  return lane.key === GROUP_LANE ? "Varias personas" : "Sin asignar";
}

export function RunTimeline({ timeline }: { timeline: Timeline }) {
  return (
    <>
      <div aria-hidden="true">
        {timeline.lanes.map((lane) => (
          <div key={lane.key} className="border-t border-border/50 py-2 first:border-t-0">
            <p className="text-sm text-text">{laneTitle(lane)}</p>
            {lane.rows.map((row) => (
              <div key={row.label} className={`${columns} mt-1`}>
                <span className="truncate text-xs text-muted">{findingLabelText[row.label]}</span>
                <div className="relative h-4 rounded-sm bg-raised">
                  {row.bars.map((bar) => (
                    <span
                      key={bar.finding.id}
                      title={`${findingLabelText[bar.finding.label]}, de ${formatClock(bar.finding.start_s)} a ${formatClock(bar.finding.end_s)}`}
                      className={`absolute top-0 h-4 rounded-sm ${barTone[row.label] ?? "bg-accent"}`}
                      style={{
                        left: `${bar.left}%`,
                        width: `${Math.min(bar.width, 100 - bar.left)}%`,
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ))}
        <div className={`${columns} mt-1 border-t border-border pt-1`}>
          <span />
          <div className="relative h-4 text-xs text-muted tabular-nums">
            {timeline.ticks.map((tick) => (
              <span
                key={tick}
                className={`absolute top-0 max-sm:nth-[even]:hidden ${tickAlign(tick, timeline.duration)}`}
                style={{ left: `${(tick / timeline.duration) * 100}%` }}
              >
                {formatClock(tick)}
              </span>
            ))}
          </div>
        </div>
      </div>
      {timeline.quiet.length > 0 && (
        <p className="mt-3 text-sm text-muted">
          Sin hallazgos: {formatList(timeline.quiet.map((member) => member.code))}.
        </p>
      )}
    </>
  );
}
