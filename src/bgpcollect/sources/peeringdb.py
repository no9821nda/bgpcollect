"""PeeringDB helper: обнаружение сиблинг-ASN по организации.

Используется командой `discover` для сопровождения seed-списка ASN (не в рантайме pipeline).
asn -> net.org_id -> все net этой org -> список ASN.
"""

from __future__ import annotations

import logging

import requests

API = "https://www.peeringdb.com/api"

log = logging.getLogger(__name__)


def org_id_for_asn(session: requests.Session, asn: int, *, timeout: int = 30) -> int | None:
    resp = session.get(f"{API}/net", params={"asn": asn}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    if not data:
        return None
    return data[0].get("org_id")


def asns_for_org(session: requests.Session, org_id: int, *, timeout: int = 30) -> list[int]:
    resp = session.get(f"{API}/net", params={"org_id": org_id}, timeout=timeout)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    return sorted({net["asn"] for net in data if net.get("asn")})


def discover_siblings(session: requests.Session, asns: list[int], *, timeout: int = 30) -> list[int]:
    """По набору известных ASN найти все ASN их организаций (сиблинги) для ревью."""
    found: set[int] = set(asns)
    seen_orgs: set[int] = set()
    for asn in asns:
        try:
            org_id = org_id_for_asn(session, asn, timeout=timeout)
            if org_id is None or org_id in seen_orgs:
                continue
            seen_orgs.add(org_id)
            found.update(asns_for_org(session, org_id, timeout=timeout))
        except (requests.RequestException, ValueError, KeyError) as exc:
            log.error("PeeringDB: ошибка для AS%s: %s", asn, exc)
    return sorted(found)
