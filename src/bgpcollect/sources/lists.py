"""Источник: локальный файл со списком CIDR/IP (по одному в строке).

Валидация/фильтрация выполняется в aggregate.normalize, поэтому здесь только чтение токенов.
Пути разрешаются относительно текущего рабочего каталога (в Docker — /app, см. монтирование ./lists).
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def read_list_file(path: str | Path) -> list[str]:
    """Прочитать файл-список: токены CIDR/IP без пустых строк и комментариев (#).

    Поддерживает inline-комментарии (`1.2.3.0/24  # метка`) и несколько токенов в строке
    (через пробел или запятую).
    """
    path = Path(path)
    if not path.is_file():
        log.error("Список не найден: %s", path)
        return []
    tokens: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tokens.extend(line.replace(",", " ").split())
    log.info("%s: %d записей", path, len(tokens))
    return tokens
