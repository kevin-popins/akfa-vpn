import csv
import io
from collections.abc import Sequence
from typing import Any

from app.core.config import settings


CONNECT_MESSAGE_CSV_COLUMNS = (
    "Фамилия",
    "Имя",
    "Логин",
    "Статус",
    "Отдел",
    "Профиль доступа",
    "Connect-ссылка",
    "Готовое сообщение",
)


def build_connect_link(user: Any, base_url: str | None = None) -> str:
    token = _clean(getattr(user, "subscription_token", ""))
    if not token:
        return ""
    resolved_base = (base_url if base_url is not None else settings.subscription_base_url).strip().rstrip("/")
    if not resolved_base:
        return f"/connect/{token}"
    return f"{resolved_base}/connect/{token}"


def connect_message_recipient(user: Any) -> str:
    first_name = _clean(getattr(user, "first_name", ""))
    last_name = _clean(getattr(user, "last_name", ""))
    if first_name and last_name:
        return f"{last_name} {first_name}"

    display_name = _clean(getattr(user, "display_name", ""))
    if display_name:
        return display_name

    username = _clean(getattr(user, "username", ""))
    if username:
        return username

    return "пользователь"


def build_connect_message(user: Any, connect_link: str) -> str:
    link = _clean(connect_link) or "Нет connect-ссылки"
    return (
        f"Уважаемый/ая {connect_message_recipient(user)}!\n\n"
        "Это ваша ссылка для подключения к AKFA VPN:\n\n"
        f"{link}\n\n"
        "Перейдите по ссылке и действуйте согласно инструкциям на странице.\n"
        "Не передавайте эту ссылку другим пользователям."
    )


def build_connect_messages_csv(users: Sequence[Any], base_url: str | None = None) -> bytes:
    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.DictWriter(output, fieldnames=CONNECT_MESSAGE_CSV_COLUMNS, lineterminator="\r\n")
    writer.writeheader()
    for user in users:
        connect_link = build_connect_link(user, base_url)
        department = getattr(user, "department", None)
        profile = getattr(user, "access_profile", None)
        writer.writerow(
            {
                "Фамилия": _clean(getattr(user, "last_name", "")),
                "Имя": _clean(getattr(user, "first_name", "")),
                "Логин": _clean(getattr(user, "username", "")),
                "Статус": _clean(getattr(user, "status", "")),
                "Отдел": _clean(getattr(department, "name", "")),
                "Профиль доступа": _clean(getattr(profile, "name", "")),
                "Connect-ссылка": connect_link or "Нет connect-ссылки",
                "Готовое сообщение": build_connect_message(user, connect_link),
            }
        )
    return output.getvalue().encode("utf-8")


def _clean(value: object) -> str:
    return str(value or "").strip()
