import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

const groupClass = "inline-flex flex-wrap items-center gap-1 rounded-full bg-raised p-1";
const itemClass =
  "rounded-full px-3.5 py-2 text-sm font-medium transition-colors duration-150 [@media(pointer:coarse)]:py-2.5";

export function Segmented({ label, children }: { label: string; children: ReactNode }) {
  return (
    <fieldset className={cn(groupClass, "m-0 min-w-0 border-0")}>
      <legend className="sr-only">{label}</legend>
      {children}
    </fieldset>
  );
}

export function SegmentedNav({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav aria-label={label} className={groupClass}>
      {children}
    </nav>
  );
}

export function SegmentedLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <a
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(itemClass, active ? "bg-text text-on-accent" : "text-muted hover:text-text")}
    >
      {children}
    </a>
  );
}

export function SegmentedButton({
  active,
  children,
  ...props
}: {
  active: boolean;
  children: ReactNode;
} & Omit<React.ComponentProps<"button">, "children">) {
  return (
    <button
      type="button"
      aria-pressed={active}
      className={cn(itemClass, active ? "bg-text text-on-accent" : "text-muted hover:text-text")}
      {...props}
    >
      {children}
    </button>
  );
}
