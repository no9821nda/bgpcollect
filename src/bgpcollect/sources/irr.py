"""IRR helper: расширение AS-SET в список ASN (через IRRd `!i`).

Используется опционально (--expand-as-sets) и в команде `discover`.
AS-SET бывают избыточны, поэтому результат — подсказки для ручного ревью, а не авто-включение.
"""

from __future__ import annotations

import logging
import re

from .official import query_irrd

log = logging.getLogger(__name__)

_AS_RE = re.compile(r"^AS(\d+)$", re.IGNORECASE)


def expand_as_set(as_set: str, *, server: str = "whois.radb.net", timeout: int = 30) -> list[int]:
    """Рекурсивно раскрыть AS-SET в отсортированный список номеров ASN.

    IRRd `!i<as-set>,1` возвращает членов рекурсивно (пробел-разделённые ASxxxx / вложенные set'ы,
    но с ,1 они уже раскрыты до ASN).
    """
    tokens = query_irrd(server, f"!i{as_set},1", timeout=timeout)
    asns: set[int] = set()
    for tok in tokens:
        m = _AS_RE.match(tok.strip())
        if m:
            asns.add(int(m.group(1)))
    log.info("AS-SET %s -> %d ASN", as_set, len(asns))
    return sorted(asns)
