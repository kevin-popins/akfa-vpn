import type { HTMLAttributes } from "react";

import { cn } from "../../lib/utils";

export function Table({ className, ...props }: HTMLAttributes<HTMLTableElement>) {
  return <table className={cn("w-full border-collapse text-left text-sm", className)} {...props} />;
}

export function StatusBadge({ value }: { value: string }) {
  const labels: Record<string, string> = {
    active: "Активен",
    disabled: "Отключен",
    expired: "Истек",
    traffic_limited: "Лимит",
    deleted: "Удален",
    draft: "Черновик",
    checking: "Проверка",
    online: "Онлайн",
    offline: "Не в сети",
    installing: "Установка",
    failed: "Ошибка",
    maintenance: "Обслуживание",
    full_tunnel: "Весь трафик через VPN",
    ru_direct: "Российские сервисы напрямую",
    custom_direct_domains: "Пользовательские direct-домены",
    vless_uri: "VLESS URI",
    xray_json: "Xray JSON",
    sing_box: "sing-box JSON",
    secure_cookies: "Защищенные cookies",
    totp_2fa: "2FA TOTP",
    csrf: "CSRF-защита"
  };
  const tone =
    value === "active" || value === "online"
      ? "border-green-200 bg-green-50 text-akfa-green"
      : value === "failed" || value === "deleted" || value === "traffic_limited"
        ? "border-red-200 bg-red-50 text-akfa-red"
        : value === "offline"
          ? "border-zinc-200 bg-zinc-50 text-zinc-600"
          : "border-amber-200 bg-amber-50 text-akfa-gold";
  const pulseDot = value === "online" ? <span className="akfa-online-dot" aria-hidden="true" /> : null;
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${tone}`}>{pulseDot}{labels[value] || value}</span>;
}
