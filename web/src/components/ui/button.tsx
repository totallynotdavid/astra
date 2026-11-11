import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 rounded-sm px-4 text-base font-medium whitespace-nowrap transition-colors duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:text-faint",
  {
    variants: {
      variant: {
        default: "bg-accent text-neutral-1 hover:bg-accent-text",
        outline: "border border-border-strong text-text hover:bg-raised",
        ghost: "text-muted hover:bg-raised hover:text-text",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export function Button({
  className,
  variant,
  type = "button",
  ...props
}: ComponentProps<"button"> & VariantProps<typeof buttonVariants>) {
  return <button className={cn(buttonVariants({ variant }), className)} type={type} {...props} />;
}

export { buttonVariants };
