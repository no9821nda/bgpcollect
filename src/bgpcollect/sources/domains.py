"""Источник: резолв доменов в IPv4 (A-записи) через системный резолвер.

Внимание: даёт лишь те адреса, которые резолвер вернул в момент запуска. Для CDN/round-robin
набор IP нестабилен и неполон — это дополнение, не замена сбора по ASN.
"""

from __future__ import annotations

import logging
import socket

log = logging.getLogger(__name__)


def resolve_domain(name: str) -> list[str]:
    """Вернуть IPv4-адреса (A-записи) одного домена."""
    try:
        infos = socket.getaddrinfo(name, None, family=socket.AF_INET, type=socket.SOCK_STREAM)
    except OSError as exc:
        log.error("DNS: не удалось разрешить %s: %s", name, exc)
        return []
    ips = sorted({info[4][0] for info in infos})
    log.info("DNS %s -> %s", name, ips)
    return ips


def resolve_domains(domains: list[str]) -> list[str]:
    """Резолвит список доменов в отсортированное множество IPv4 (в /32 их превратит normalize)."""
    found: set[str] = set()
    for name in domains:
        found.update(resolve_domain(name))
    return sorted(found)
