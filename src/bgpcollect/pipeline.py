"""Оркестрация: сбор -> агрегация -> рендер -> дифф/guardrail -> запись в dist/."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import aggregate, render
from .config import Config, Service, SourceSet
from .sources import domains as domain_src
from .sources import irr
from .sources import lists as list_src
from .sources import official, ripestat

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


def _expand_asns(
    asns: list[int],
    as_sets: list[str],
    *,
    expand_as_sets: bool = False,
    irr_server: str = "whois.radb.net",
) -> list[int]:
    result = set(asns)
    if expand_as_sets:
        for as_set in as_sets:
            try:
                result.update(irr.expand_as_set(as_set, server=irr_server))
            except OSError as exc:
                log.error("Не удалось раскрыть %s: %s", as_set, exc)
    return sorted(result)


def effective_asns(
    service: Service,
    *,
    expand_as_sets: bool = False,
    irr_server: str = "whois.radb.net",
) -> list[int]:
    """Итоговый набор ASN сервиса: seed + опц. раскрытие AS-SET."""
    return _expand_asns(
        service.asns, service.as_sets, expand_as_sets=expand_as_sets, irr_server=irr_server
    )


def _gather(
    session: requests.Session,
    settings,
    src: SourceSet,
    *,
    expand_as_sets: bool = False,
) -> tuple[list[str], list[str], list[int]]:
    """Собрать «сырые» префиксы из набора источников. Вернуть (raw, sources, asns)."""
    raw: list[str] = []
    sources: list[str] = []
    asns = _expand_asns(src.asns, src.as_sets, expand_as_sets=expand_as_sets)

    if asns:
        ris = ripestat.fetch_many(session, asns, sourceapp=settings.ripestat_sourceapp)
        for prefixes in ris.values():
            raw.extend(prefixes)
        sources.append(f"ripestat-ris(AS×{len(asns)})")

    for s in src.official:
        raw.extend(official.fetch_official(session, s))
        sources.append(f"official:{s.type}")

    if src.static_prefixes:
        raw.extend(src.static_prefixes)
        sources.append("static")

    for rel in src.lists:
        prefixes = list_src.read_list_file(rel)
        if prefixes:
            raw.extend(prefixes)
            sources.append(f"list:{Path(rel).name}")

    if src.domains:
        ips = domain_src.resolve_domains(src.domains)
        if ips:
            raw.extend(ips)
            sources.append(f"domains×{len(src.domains)}")

    return raw, sources, asns


def collect_service(
    config: Config,
    service: Service,
    session: requests.Session,
    *,
    expand_as_sets: bool = False,
) -> tuple[list[aggregate.IPv4Network], list[str], int, list[int]]:
    """Собрать и агрегировать IPv4-сети одного сервиса (с учётом exclude-вычитания)."""
    settings = config.settings

    # include — собственные источники сервиса.
    raw, sources, asns = _gather(
        session, settings, service.source_set(), expand_as_sets=expand_as_sets
    )
    networks = aggregate.aggregate(raw, min_prefixlen=settings.min_ipv4_prefixlen)

    # exclude — вычитаем эти диапазоны из результата (например, GCP cloud.json у Google).
    if not service.exclude.is_empty():
        exc_raw, exc_sources, _ = _gather(
            session, settings, service.exclude, expand_as_sets=expand_as_sets
        )
        # для exclude не отсекаем широкие диапазоны (min_prefixlen=1), чтобы вычесть их целиком
        exc_nets = aggregate.aggregate(exc_raw, min_prefixlen=1)
        before = len(networks)
        networks = aggregate.subtract(networks, exc_nets)
        sources.append("exclude[" + ", ".join(exc_sources) + "]")
        log.info("%s: exclude убрал %d -> %d префиксов", service.name, before, len(networks))

    log.info(
        "%s: raw=%d -> %d префиксов (источники: %s)",
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
