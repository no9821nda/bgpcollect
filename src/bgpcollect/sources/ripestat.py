"""RIPEstat — основной источник: реально анонсируемые префиксы по ASN (данные RIS).

API: https://stat.ripe.net/docs/data-api/api-endpoints/announced-prefixes
GET https://stat.ripe.net/data/announced-prefixes/data.json?resource=AS15169
"""

from __future__ import annotations

import logging

import requests

ANNOUNCED_PREFIXES_URL = "https://stat.ripe.net/data/announced-prefixes/data.json"

log = logging.getLogger(__name__)


def fetch_announced_prefixes(
    session: requests.Session,
    asn: int,
    *,
    sourceapp: str = "bgpcollect",
    timeout: int = 30,
) -> list[str]:
    """Вернуть список CIDR-строк (v4 и v6), анонсируемых данным ASN по данным RIS.

    Фильтрация по версии IP делается выше (в aggregate.normalize).
    """
    params = {"resource": f"AS{asn}", "sourceapp": sourceapp}
    resp = session.get(ANNOUNCED_PREFIXES_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()

    status = payload.get("status")
    if status != "ok":
        log.warning("RIPEstat вернул status=%s для AS%s", status, asn)

    data = payload.get("data") or {}
    prefixes = [item["prefix"] for item in data.get("prefixes", []) if item.get("prefix")]
    log.info("AS%s: RIPEstat вернул %d префиксов", asn, len(prefixes))
    return prefixes


def fetch_many(
    session: requests.Session,
    asns: list[int],
    *,
    sourceapp: str = "bgpcollect",
    timeout: int = 30,
) -> dict[int, list[str]]:
    """Собрать префиксы для набора ASN. Ошибку по одному ASN логируем и продолжаем."""
    result: dict[int, list[str]] = {}
    for asn in asns:
        try:
            result[asn] = fetch_announced_prefixes(
                session, asn, sourceapp=sourceapp, timeout=timeout
            )
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.error("Не удалось получить префиксы для AS%s: %s", asn, exc)
            result[asn] = []
    return result
