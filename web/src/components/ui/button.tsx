import { cva, type VariantProps } from "class-variance-authority";
import type { ComponentProps } from "react";

import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex h-10 items-center justify-center gap-2 rounded-full px-5 text-sm font-medium whitespace-nowrap transition-[background-color,color,box-shadow,scale] duration-150 ease-out active:scale-[0.97] disabled:pointer-events-none disabled:text-faint",
  {
    variants: {
      variant: {
        default: "bg-accent text-on-accent hover:bg-neutral-9",
        outline: "bg-surface text-text shadow-raised hover:bg-raised",
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
