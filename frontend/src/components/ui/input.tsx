import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn("focus-ring h-10 w-full rounded-md border border-akfa-line bg-white px-3 text-sm", className)}
      {...props}
    />
  );
}

export function Textarea({ className, ...props }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn("focus-ring min-h-24 w-full rounded-md border border-akfa-line bg-white px-3 py-2 text-sm", className)}
      {...props}
    />
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn("focus-ring h-10 w-full rounded-md border border-akfa-line bg-white px-3 text-sm", className)}
      {...props}
    />
  );
}

export function Field({ label, children, hint, error }: { label: string; children: ReactNode; hint?: string; error?: string }) {
  return (
    <label className="grid min-w-0 gap-1.5 text-sm font-medium text-akfa-ink">
      <span>{label}</span>
      {children}
      {error ? <span className="text-xs font-normal text-akfa-red">{error}</span> : null}
      {!error && hint ? <span className="text-xs font-normal text-akfa-muted">{hint}</span> : null}
    </label>
  );
}
