import {
  Activity,
  ClipboardList,
  Download,
  Gauge,
  KeyRound,
  Layers,
  Lock,
  Server,
  Settings,
  ShieldCheck,
  Upload,
  UserCog,
  Users,
  Menu,
  X
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { Button } from "./ui/button";

export type PageKey =
  | "dashboard"
  | "servers"
  | "add-server"
  | "server-detail"
  | "install-xray"
  | "departments"
  | "department-detail"
  | "profiles"
  | "profile-editor"
  | "users"
  | "user-detail"
  | "bulk-import"
  | "subscription-preview"
  | "config-preview"
  | "traffic"
  | "backup"
  | "audit"
  | "settings";

const nav = [
  { key: "dashboard", label: "Дашборд", icon: Gauge },
  { key: "servers", label: "Серверы", icon: Server },
  { key: "add-server", label: "Добавить VPS", icon: KeyRound },
  { key: "install-xray", label: "Установка Xray", icon: ShieldCheck },
  { key: "departments", label: "Отделы", icon: Layers },
  { key: "profiles", label: "Профили доступа", icon: Lock },
  { key: "users", label: "Пользователи VPN", icon: Users },
  { key: "bulk-import", label: "Массовый импорт", icon: Upload },
  { key: "traffic", label: "Аналитика трафика", icon: Activity },
  { key: "backup", label: "Бэкап", icon: Download },
  { key: "audit", label: "Журнал аудита", icon: ClipboardList },
  { key: "settings", label: "Настройки администратора", icon: UserCog }
] as const;

export function Layout({
  page,
  onPage,
  children,
}: {
  page: PageKey;
  onPage: (page: PageKey) => void;
  children: ReactNode;
}) {
  const title = nav.find((item) => item.key === page)?.label || "AKFA";
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [mobileOpen]);

  const sidebar = (
    <>
      <div className="flex h-16 items-center justify-between gap-3 border-b border-akfa-line px-5">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-md bg-akfa-red text-lg font-bold text-white">A</div>
          <div>
            <div className="text-lg font-semibold">AKFA</div>
            <div className="text-xs text-akfa-muted">Управление доступом</div>
          </div>
        </div>
        <button className="rounded-md p-2 text-zinc-600 hover:bg-akfa-soft lg:hidden" type="button" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)}>
          <X size={18} />
        </button>
      </div>
      <nav className="grid gap-1 overflow-y-auto p-3">
        {nav.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              onClick={() => {
                onPage(item.key);
                setMobileOpen(false);
              }}
              className={`flex h-10 items-center gap-3 rounded-md px-3 text-sm transition ${
                page === item.key ? "bg-red-50 font-medium text-akfa-red" : "text-zinc-700 hover:bg-akfa-soft"
              }`}
            >
              <Icon size={18} />
              <span className="truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>
    </>
  );

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 hidden w-64 border-r border-akfa-line bg-white lg:block">
        {sidebar}
      </aside>
      {mobileOpen ? (
        <div className="fixed inset-0 z-40 lg:hidden">
          <button className="absolute inset-0 bg-zinc-950/35" type="button" aria-label="Закрыть меню" onClick={() => setMobileOpen(false)} />
          <aside className="relative flex h-full w-[260px] flex-col border-r border-akfa-line bg-white shadow-xl">
            {sidebar}
          </aside>
        </div>
      ) : null}
      <main className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-akfa-line bg-white/95 px-4 backdrop-blur lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <button className="rounded-md border border-akfa-line bg-white p-2 text-zinc-700 hover:border-akfa-red lg:hidden" type="button" aria-label="Открыть меню" onClick={() => setMobileOpen(true)}>
              <Menu size={20} />
            </button>
            <div className="min-w-0">
            <div className="text-sm text-akfa-muted">Администрирование интернет-доступа</div>
            <h1 className="truncate text-xl font-semibold">{title}</h1>
            </div>
          </div>
          <Button variant="secondary" onClick={() => window.location.reload()}>
            <Settings size={16} />
            Обновить
          </Button>
        </header>
        <div className="w-full px-4 py-6 lg:px-6 xl:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}
