import type { DashboardState } from "../data/store";
import { EventList } from "../components/EventList";
import { InsightCard } from "../components/InsightCard";
import { EmptyView } from "../components/StateView";
import { Card, CardTitle } from "../components/ui/card";
import { sourceForSession } from "../lib/status";

export function Insights({ state }: { state: DashboardState }) {
  const insights = [...state.insights].reverse();

  return (
    <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
      <div className="space-y-4">
        {insights.length === 0 ? (
          <EmptyView title="Todavía no hay análisis">
            El análisis revisa cada lectura y señala patrones para que una persona los evalúe. No
            emite diagnósticos.
          </EmptyView>
        ) : (
          insights.map((insight) => (
            <InsightCard
              key={`${insight.session_id}-${insight.seq}`}
              insight={insight}
              source={sourceForSession(state.sessions, insight.session_id)}
            />
          ))
        )}
      </div>
      <Card className="h-fit p-4">
        <CardTitle>Eventos</CardTitle>
        <div className="mt-2">
          <EventList events={state.events} />
        </div>
      </Card>
    </div>
  );
}
