import type { ButtonHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
};

export function Button({ className, variant = "primary", ...props }: ButtonProps) {
  const variants = {
    primary: "bg-akfa-red text-white hover:bg-red-700",
    secondary: "bg-white text-akfa-ink border border-akfa-line hover:border-akfa-red",
    ghost: "bg-transparent text-akfa-ink hover:bg-akfa-soft",
    danger: "bg-red-50 text-akfa-red border border-red-200 hover:bg-red-100"
  };
  return (
    <button
      className={cn(
        "inline-flex h-10 items-center justify-center gap-2 rounded-md px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        variants[variant],
        className
      )}
      {...props}
    />
  );
}

