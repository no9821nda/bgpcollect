"""Загрузка и валидация config/services.yaml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class OfficialSource:
    type: str  # "google_json" | "whois_asset"
    url: str | None = None
    server: str | None = None
    query: str | None = None


@dataclass
class SourceSet:
    """Набор источников IP (используется и для сбора, и для exclude-вычитания)."""
    asns: list[int] = field(default_factory=list)
    as_sets: list[str] = field(default_factory=list)
    official: list[OfficialSource] = field(default_factory=list)
    static_prefixes: list[str] = field(default_factory=list)
    lists: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (
            self.asns or self.as_sets or self.official
            or self.static_prefixes or self.lists or self.domains
        )


@dataclass
class Service:
    name: str
    description: str = ""
    asns: list[int] = field(default_factory=list)
    as_sets: list[str] = field(default_factory=list)
    official: list[OfficialSource] = field(default_factory=list)
    static_prefixes: list[str] = field(default_factory=list)
    lists: list[str] = field(default_factory=list)      # пути к файлам со списками CIDR/IP
    domains: list[str] = field(default_factory=list)    # домены для резолва в A-записи
    exclude: SourceSet = field(default_factory=SourceSet)  # вычесть эти диапазоны из результата
    parent: str | None = None

    def source_set(self) -> SourceSet:
        """Собственные источники сервиса как SourceSet (то, что собираем = include)."""
        return SourceSet(
            asns=self.asns, as_sets=self.as_sets, official=self.official,
            static_prefixes=self.static_prefixes, lists=self.lists, domains=self.domains,
        )


@dataclass
class Settings:
    min_ipv4_prefixlen: int = 8
    ripestat_sourceapp: str = "bgpcollect"
    max_shrink_ratio: float = 0.5


@dataclass
class Config:
    settings: Settings
    services: dict[str, Service]

    def service(self, name: str) -> Service:
        try:
            return self.services[name]
        except KeyError:
            raise KeyError(
                f"Неизвестный сервис '{name}'. Доступны: {', '.join(sorted(self.services))}"
            ) from None


def _parse_official(raw: list[dict]) -> list[OfficialSource]:
    sources: list[OfficialSource] = []
    for item in raw or []:
        stype = item.get("type")
        if stype not in {"google_json", "whois_asset"}:
            raise ValueError(f"Неизвестный type официального источника: {stype!r}")
        sources.append(
            OfficialSource(
                type=stype,
                url=item.get("url"),
                server=item.get("server"),
                query=item.get("query"),
            )
        )
    return sources


def _parse_source_set(raw: dict) -> SourceSet:
    raw = raw or {}
    return SourceSet(
        asns=[int(a) for a in raw.get("asns", [])],
        as_sets=list(raw.get("as_sets", [])),
        official=_parse_official(raw.get("official", [])),
        static_prefixes=list(raw.get("static_prefixes", [])),
        lists=[str(p) for p in raw.get("lists", [])],
        domains=[str(d) for d in raw.get("domains", [])],
    )


def load_config(path: str | Path) -> Config:
    """Прочитать и провалидировать конфиг сервисов."""
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    settings = Settings(**(data.get("settings") or {}))

    services: dict[str, Service] = {}
    for name, raw in (data.get("services") or {}).items():
        raw = raw or {}
        services[name] = Service(
            name=name,
            description=raw.get("description", ""),
            asns=[int(a) for a in raw.get("asns", [])],
            as_sets=list(raw.get("as_sets", [])),
            official=_parse_official(raw.get("official", [])),
            static_prefixes=list(raw.get("static_prefixes", [])),
            lists=[str(p) for p in raw.get("lists", [])],
            domains=[str(d) for d in raw.get("domains", [])],
            exclude=_parse_source_set(raw.get("exclude", {})),
            parent=raw.get("parent"),
        )

    if not services:
        raise ValueError(f"В {path} нет ни одного сервиса")

    # Проверка ссылок parent.
    for svc in services.values():
        if svc.parent and svc.parent not in services:
            raise ValueError(
                f"Сервис '{svc.name}' ссылается на несуществующий parent '{svc.parent}'"
            )

    return Config(settings=settings, services=services)
