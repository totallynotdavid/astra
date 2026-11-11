import type { ComponentProps } from "react";

import { cn } from "../../lib/utils";

export function Skeleton({ className, ...props }: ComponentProps<"div">) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded-sm bg-raised", className)}
      {...props}
    />
  );
}
