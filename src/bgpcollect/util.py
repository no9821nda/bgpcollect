"""Общие утилиты."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: str) -> None:
    """Атомарно записать текстовый файл: tmp в том же каталоге + os.replace.

    Параллельные читатели (nginx, bird-reloader) видят либо старую, либо новую
    версию целиком — никогда частичную запись.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        # mkstemp создаёт файл 0600 — вернём обычные права, иначе nginx/хост не прочитают
        os.chmod(tmp_name, 0o644)
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
