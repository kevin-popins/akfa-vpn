import { AlertTriangle } from "lucide-react";

import { Button } from "./ui/button";

export function ConfirmDialog({
  open,
  title,
  text,
  confirmLabel = "Подтвердить",
  onConfirm,
  onCancel
}: {
  open: boolean;
  title: string;
  text: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-zinc-950/20 p-4">
      <div className="w-full max-w-md rounded-lg border border-akfa-line bg-white p-5 shadow-panel">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-full bg-red-50 text-akfa-red">
            <AlertTriangle size={20} />
          </span>
          <div>
            <h2 className="text-base font-semibold">{title}</h2>
            <p className="mt-1 text-sm text-akfa-muted">{text}</p>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>
            Отмена
          </Button>
          <Button variant="danger" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
