import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(value?: number | null) {
  if (!value) return "0 Б";
  const units = ["Б", "КБ", "МБ", "ГБ", "ТБ"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const rounded = unit ? Number(size.toFixed(1)) : Math.round(size);
  return `${rounded} ${units[unit]}`;
}

export type ConnectMessageUser = {
  first_name?: string | null;
  last_name?: string | null;
  display_name?: string | null;
  username?: string | null;
};

export function buildConnectMessage(user: ConnectMessageUser, connectLink: string) {
  const recipient = connectMessageRecipient(user);
  const link = connectLink.trim() || "Нет connect-ссылки";
  return [
    `Уважаемый/ая ${recipient}!`,
    "",
    "Это ваша ссылка для подключения к AKFA VPN:",
    "",
    link,
    "",
    "Перейдите по ссылке и действуйте согласно инструкциям на странице.",
    "Не передавайте эту ссылку другим пользователям."
  ].join("\n");
}

function connectMessageRecipient(user: ConnectMessageUser) {
  const firstName = (user.first_name || "").trim();
  const lastName = (user.last_name || "").trim();
  if (firstName && lastName) return `${lastName} ${firstName}`;
  const displayName = (user.display_name || "").trim();
  if (displayName) return displayName;
  const username = (user.username || "").trim();
  return username || "пользователь";
}
