"""Рендереры выходных форматов из списка агрегированных IPv4-сетей.

Каждый рендерер: (name, networks, meta) -> str (содержимое файла).
Реестр RENDERERS отображает имя_файла -> функция.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable

IPv4Network = ipaddress.IPv4Network
Meta = dict


def _header(name: str, networks: list[IPv4Network], meta: Meta, comment: str) -> str:
    """Шапка-комментарий с метаданными. `comment` — префикс комментария формата."""
    lines = [
        f"{comment} bgpcollect — IPv4-сети сервиса: {name}",
        f"{comment} prefixes: {len(networks)}",
        f"{comment} generated_at: {meta.get('generated_at', 'n/a')}",
        f"{comment} sources: {', '.join(meta.get('sources', [])) or 'n/a'}",
    ]
    return "\n".join(lines) + "\n"


def render_plain(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """Голый список CIDR, по одному в строке (без комментариев — для машинного чтения)."""
    return "".join(f"{net}\n" for net in networks)


def render_plain_commented(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """Список CIDR с шапкой-комментарием."""
    return _header(name, networks, meta, "#") + render_plain(name, networks, meta)


def render_mikrotik(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """MikroTik RouterOS: address-list."""
    out = [_header(name, networks, meta, "#"), "/ip firewall address-list"]
    for net in networks:
        out.append(f"add list={name} address={net}")
    return "\n".join(out) + "\n"


def render_nftables(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """nftables: именованный set с элементами-сетями."""
    if not networks:
        # пустой define невалиден/бессмыслен — отдаём только предупреждение
        return _header(name, networks, meta, "#") + "# ПУСТО: префиксов нет, set не сгенерирован.\n"
    elems = ",\n        ".join(str(net) for net in networks)
    body = (
        f"define {name}_v4 = {{\n        {elems}\n}}\n\n"
        f"# Пример использования:\n"
        f"# table inet filter {{\n"
        f"#   set {name}_v4 {{ type ipv4_addr; flags interval; elements = $" + f"{name}_v4 }}\n"
        f"# }}\n"
    )
    return _header(name, networks, meta, "#") + body


def render_ipset(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """ipset (restore-формат): create + add."""
    out = [
        _header(name, networks, meta, "#"),
        f"create {name} hash:net family inet hashsize 4096 maxelem 1000000 -exist",
    ]
    for net in networks:
        out.append(f"add {name} {net} -exist")
    return "\n".join(out) + "\n"


def render_wireguard(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """WireGuard: строка AllowedIPs (через запятую)."""
    if not networks:
        # пустое `AllowedIPs = ` заблокировало бы клиенту весь трафик — не отдаём его
        return _header(name, networks, meta, "#") + "# ПУСТО: префиксов нет, AllowedIPs не сгенерирован.\n"
    allowed = ", ".join(str(net) for net in networks)
    return _header(name, networks, meta, "#") + f"AllowedIPs = {allowed}\n"


def render_cisco(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """Cisco IOS: ip prefix-list."""
    out = [_header(name, networks, meta, "!")]
    for net in networks:
        out.append(f"ip prefix-list {name} permit {net}")
    return "\n".join(out) + "\n"


def render_meta(name: str, networks: list[IPv4Network], meta: Meta) -> str:
    """meta.json — статистика и метаданные запуска."""
    payload = dict(meta)
    payload["service"] = name
    payload["prefix_count"] = len(networks)
    payload["address_count"] = sum(net.num_addresses for net in networks)
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


# Имя_файла -> рендерер.
RENDERERS: dict[str, Callable[[str, list[IPv4Network], Meta], str]] = {
    "ipv4.txt": render_plain,
    "ipv4-commented.txt": render_plain_commented,
    "mikrotik.rsc": render_mikrotik,
    "nftables.conf": render_nftables,
    "ipset.txt": render_ipset,
    "wireguard.txt": render_wireguard,
    "cisco.txt": render_cisco,
    "meta.json": render_meta,
}


def render_all(name: str, networks: list[IPv4Network], meta: Meta) -> dict[str, str]:
    """Сгенерировать все форматы. Вернуть {имя_файла: содержимое}."""
    return {fname: fn(name, networks, meta) for fname, fn in RENDERERS.items()}
