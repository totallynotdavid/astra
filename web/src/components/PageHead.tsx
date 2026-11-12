import type { ReactNode } from "react";

export function PageHead({
  title,
  note,
  aside,
}: {
  title: string;
  note?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="max-w-prose">
        <h1 className="text-2xl font-semibold tracking-tight text-text sm:text-3xl">{title}</h1>
        {note && <p className="mt-2 text-sm text-muted">{note}</p>}
      </div>
      {aside && <div className="flex items-center gap-2">{aside}</div>}
    </div>
  );
}
