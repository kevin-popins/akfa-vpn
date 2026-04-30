import re
from collections.abc import Iterable


def normalize_blocked_domains(values: Iterable[str] | None) -> list[str]:
    if not values:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value).strip().lower().rstrip(".")
        if not value:
            continue
        if "://" in value:
            raise ValueError("Укажите домен без http:// или https://")
        if any(char.isspace() for char in value):
            raise ValueError("Домен блокировки не должен содержать пробелы")
        if "/" in value or "\\" in value:
            raise ValueError("Домен блокировки не должен содержать путь")
        if ":" in value:
            raise ValueError("Домен блокировки не должен содержать порт")
        if "*" in value:
            raise ValueError("Укажите домен без wildcard-символов")
        labels = value.split(".")
        if len(labels) < 2 or any(not label for label in labels):
            raise ValueError("Укажите корректный домен для блокировки")
        if value not in seen:
            seen.add(value)
            normalized.append(value)
    return normalized


def blocked_domain_matchers(values: Iterable[str] | None) -> list[str]:
    return [f"regexp:^(.+\\.)?{re.escape(domain)}$" for domain in normalize_blocked_domains(values)]
