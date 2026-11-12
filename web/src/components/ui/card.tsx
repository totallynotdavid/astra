import type { ComponentProps } from "react";

import { cn } from "../../lib/utils";

export function Card({ className, ...props }: ComponentProps<"section">) {
  return (
    <section className={cn("rounded-panel bg-surface p-6 shadow-raised", className)} {...props} />
  );
}

export function CardTitle({ className, children, ...props }: ComponentProps<"h2">) {
  return (
    <h2 className={cn("text-base font-medium", className)} {...props}>
      {children}
    </h2>
  );
}
