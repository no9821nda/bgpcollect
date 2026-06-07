"""Нормализация и агрегация IPv4-префиксов.

Используем стандартный модуль ipaddress:
  * надёжная классификация (private/reserved/multicast/...) без сторонних зависимостей;
  * collapse_addresses() убирает вложенные и склеивает смежные префиксы (= cidr_merge/aggregate6).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterable

IPv4Network = ipaddress.IPv4Network


def parse_ipv4(prefix: str) -> IPv4Network | None:
    """Распарсить строку в IPv4Network (strict=False). Вернуть None, если это не IPv4-сеть."""
    prefix = prefix.strip()
    if not prefix:
        return None
    try:
        net = ipaddress.ip_network(prefix, strict=False)
    except ValueError:
        return None
    if not isinstance(net, ipaddress.IPv4Network):
        return None
    return net


def is_acceptable(net: IPv4Network, min_prefixlen: int) -> bool:
    """Пускаем только глобально-маршрутизируемый публичный IPv4 разумного размера."""
    if net.prefixlen < min_prefixlen or net.prefixlen > 32:
        return False
    if not net.is_global:
        return False
    # is_global уже отсекает большинство спец-диапазонов, но подстрахуемся явно.
    if net.is_multicast or net.is_reserved or net.is_loopback or net.is_unspecified:
        return False
    return True


def normalize(
    prefixes: Iterable[str],
    *,
    min_prefixlen: int = 8,
) -> list[IPv4Network]:
    """Строки -> валидные публичные IPv4-сети (без дублей, без bogon/private/слишком широких)."""
    seen: set[IPv4Network] = set()
    for raw in prefixes:
        net = parse_ipv4(raw)
        if net is None:
            continue
        if not is_acceptable(net, min_prefixlen):
            continue
        seen.add(net)
    return sorted(seen)


def merge(networks: Iterable[IPv4Network]) -> list[IPv4Network]:
    """Агрегировать: убрать вложенные, склеить смежные (192.0.0.0/24+192.0.1.0/24 -> /23)."""
    return list(ipaddress.collapse_addresses(networks))


def aggregate(prefixes: Iterable[str], *, min_prefixlen: int = 8) -> list[IPv4Network]:
    """normalize + merge одним вызовом."""
    return merge(normalize(prefixes, min_prefixlen=min_prefixlen))


def subtract(
    includes: Iterable[IPv4Network],
    excludes: Iterable[IPv4Network],
) -> list[IPv4Network]:
    """Вычесть из includes все диапазоны excludes (set-difference по адресному пространству).

    Два CIDR-а либо не пересекаются, либо один вложен в другой — поэтому:
      * exclude покрывает include  -> include выкидываем;
      * exclude внутри include     -> режем include на части (address_exclude);
      * не пересекаются            -> оставляем.
    Результат — collapsed (склеенный) список.
    """
    work = list(merge(includes))
    exc_list = list(merge(excludes))
    for exc in exc_list:
        nxt: list[IPv4Network] = []
        for net in work:
            if net.subnet_of(exc):          # include целиком внутри exclude (вкл. равенство) — убираем
                continue
            if exc.subnet_of(net):           # exclude строго внутри include — режем
                nxt.extend(net.address_exclude(exc))
            else:                            # не пересекаются — оставляем
                nxt.append(net)
        work = nxt
    return merge(work)


def count_addresses(networks: Iterable[IPv4Network]) -> int:
    """Сколько IPv4-адресов покрывают сети (для статистики/meta.json)."""
    return sum(net.num_addresses for net in networks)
