import { CloudOff, Satellite } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "./ui/button";
import { Skeleton } from "./ui/skeleton";

export function LoadingView() {
  return (
    <div className="space-y-6">
      <output className="sr-only">Conectando con ASTRA…</output>
      <div className="grid gap-4 sm:grid-cols-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        <Skeleton className="h-56" />
        <Skeleton className="h-56" />
      </div>
    </div>
  );
}

export function EmptyView({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-panel border border-border bg-surface p-12 text-center">
      <Satellite aria-hidden="true" className="h-8 w-8 text-muted" />
      <h2 className="text-base font-medium">{title}</h2>
      <p className="max-w-md text-sm text-muted">{children}</p>
    </div>
  );
}

export function ErrorView({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex flex-col items-center gap-3 rounded-panel border border-critical/40 bg-surface p-12 text-center"
    >
      <CloudOff aria-hidden="true" className="h-8 w-8 text-critical" />
      <h2 className="text-base font-medium">No se pudo conectar con el servidor</h2>
      <p className="max-w-md text-sm text-muted">{message}</p>
      <Button variant="outline" onClick={() => location.reload()}>
        Reintentar
      </Button>
    </div>
  );
}
