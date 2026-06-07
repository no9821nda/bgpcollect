"""Оркестрация: сбор -> агрегация -> рендер -> дифф/guardrail -> запись в dist/."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import aggregate, render
from .config import Config, Service
from .sources import irr, official, ripestat

log = logging.getLogger(__name__)


@dataclass
class ServiceResult:
    name: str
    networks: list[aggregate.IPv4Network]
    sources_used: list[str]
    raw_count: int
    asns: list[int]
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    published: bool = True
    skipped_reason: str | None = None

    @property
    def prefix_count(self) -> int:
        return len(self.networks)


def effective_asns(
    service: Service,
    *,
    expand_as_sets: bool = False,
    irr_server: str = "whois.radb.net",
) -> list[int]:
    """Итоговый набор ASN сервиса: seed + опц. раскрытие AS-SET."""
    asns = set(service.asns)
    if expand_as_sets:
        for as_set in service.as_sets:
            try:
                asns.update(irr.expand_as_set(as_set, server=irr_server))
            except OSError as exc:
                log.error("Не удалось раскрыть %s: %s", as_set, exc)
    return sorted(asns)


def collect_service(
    config: Config,
    service: Service,
    session: requests.Session,
    *,
    expand_as_sets: bool = False,
) -> tuple[list[aggregate.IPv4Network], list[str], int, list[int]]:
    """Собрать и агрегировать IPv4-сети одного сервиса."""
    settings = config.settings
    asns = effective_asns(service, expand_as_sets=expand_as_sets)

    raw: list[str] = []
    sources: list[str] = []

    # 1. Основной источник — RIPEstat/RIS по списку ASN.
    if asns:
        ris = ripestat.fetch_many(session, asns, sourceapp=settings.ripestat_sourceapp)
        for prefixes in ris.values():
            raw.extend(prefixes)
        sources.append(f"ripestat-ris(AS×{len(asns)})")

    # 2. Официальные источники.
    for src in service.official:
        prefixes = official.fetch_official(session, src)
        raw.extend(prefixes)
        sources.append(f"official:{src.type}")

    # 3. Статические диапазоны.
    if service.static_prefixes:
        raw.extend(service.static_prefixes)
        sources.append("static")

    networks = aggregate.aggregate(raw, min_prefixlen=settings.min_ipv4_prefixlen)
    log.info(
        "%s: raw=%d -> aggregated=%d префиксов (источники: %s)",
        service.name, len(raw), len(networks), ", ".join(sources),
    )
    return networks, sources, len(raw), asns


def _read_previous(path: Path) -> set[str]:
    """Прочитать предыдущий ipv4.txt (для диффа/guardrail)."""
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def run_service(
    config: Config,
    name: str,
    session: requests.Session,
    out_dir: Path,
    *,
    expand_as_sets: bool = False,
    force: bool = False,
) -> ServiceResult:
    """Полный прогон по одному сервису: собрать, сравнить, (если ок) записать форматы."""
    service = config.service(name)
    networks, sources, raw_count, asns = collect_service(
        config, service, session, expand_as_sets=expand_as_sets
    )

    svc_dir = out_dir / name
    prev = _read_previous(svc_dir / "ipv4.txt")
    current = {str(n) for n in networks}
    added = sorted(current - prev)
    removed = sorted(prev - current)

    result = ServiceResult(
        name=name, networks=networks, sources_used=sources,
        raw_count=raw_count, asns=asns, added=added, removed=removed,
    )

    # Guardrail: не публиковать, если резко обвалилось число префиксов.
    if prev and not force:
        ratio = len(current) / len(prev) if prev else 1.0
        if ratio < (1 - config.settings.max_shrink_ratio):
            result.published = False
            result.skipped_reason = (
                f"prefix-count упал {len(prev)}->{len(current)} "
                f"(< {1 - config.settings.max_shrink_ratio:.0%}); публикация пропущена (--force чтобы перезаписать)"
            )
            log.warning("%s: %s", name, result.skipped_reason)
            return result

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "asns": asns,
        "raw_prefix_count": raw_count,
        "added": len(added),
        "removed": len(removed),
    }
    _write_outputs(svc_dir, name, networks, meta)
    log.info("%s: записано в %s (+%d/-%d)", name, svc_dir, len(added), len(removed))
    return result


def _write_outputs(svc_dir: Path, name: str, networks, meta) -> None:
    svc_dir.mkdir(parents=True, exist_ok=True)
    for fname, content in render.render_all(name, networks, meta).items():
        (svc_dir / fname).write_text(content, encoding="utf-8", newline="\n")


def run_all(
    config: Config,
    services: list[str],
    session: requests.Session,
    out_dir: Path,
    *,
    expand_as_sets: bool = False,
    force: bool = False,
) -> list[ServiceResult]:
    """Прогнать список сервисов + собрать объединённый dist/all/."""
    results = [
        run_service(config, name, session, out_dir, expand_as_sets=expand_as_sets, force=force)
        for name in services
    ]

    # Объединённый список из всех опубликованных сервисов.
    combined: list[aggregate.IPv4Network] = []
    used_sources: set[str] = set()
    for r in results:
        if r.published:
            combined.extend(r.networks)
            used_sources.update(r.sources_used)
    combined = aggregate.merge(combined)
    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sorted(used_sources),
        "services": [r.name for r in results if r.published],
    }
    _write_outputs(out_dir / "all", "all", combined, meta)
    log.info("all: %d префиксов из %d сервисов", len(combined), len(meta["services"]))
    return results
