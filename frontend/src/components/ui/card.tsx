import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 rounded-lg border border-akfa-line bg-white shadow-panel", className)} {...props} />;
}

export function CardHeader({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("border-b border-akfa-line px-5 py-4", className)} {...props} />;
}

export function CardContent({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("min-w-0 px-5 py-4", className)} {...props} />;
}
