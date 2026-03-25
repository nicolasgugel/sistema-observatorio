import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "rounded-sm text-white shadow-none hover:opacity-90 [background:linear-gradient(135deg,hsl(var(--ds-primary))_0%,hsl(var(--ds-primary-container))_100%)]",
        destructive: "rounded-sm bg-destructive text-destructive-foreground shadow-none hover:bg-destructive/90",
        outline: "rounded-sm border border-[hsl(var(--ds-outline-variant)/0.15)] bg-transparent hover:bg-[hsl(var(--ds-surface-container-low))] hover:text-foreground",
        secondary: "rounded-sm bg-[hsl(var(--ds-surface-container-low))] text-foreground hover:bg-[hsl(var(--ds-surface-container-high))]",
        ghost: "rounded-sm hover:bg-[hsl(var(--ds-surface-container-low))] hover:text-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-sm px-3",
        lg: "h-11 rounded-sm px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
