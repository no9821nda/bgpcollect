"""CLI: bgpcollect collect | discover | feed."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import feed as feed_mod
from .config import load_config
from .http import make_session
from .pipeline import run_all
from .sources import irr, peeringdb

DEFAULT_CONFIG = "config/services.yaml"
DEFAULT_OUT = "dist"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )


def _resolve_services(config, arg: str) -> list[str]:
    if arg in ("all", "", None):
        return list(config.services)
    names = [s.strip() for s in arg.split(",") if s.strip()]
    for n in names:
        config.service(n)  # бросит, если неизвестен
    return names


def cmd_collect(args) -> int:
    config = load_config(args.config)
    services = _resolve_services(config, args.services)
    session = make_session()
    results = run_all(
        config, services, session, Path(args.out),
        expand_as_sets=args.expand_as_sets, force=args.force,
    )
    print(f"\n=== bgpcollect: {len(results)} сервис(ов) ===")
    for r in results:
        status = "OK" if r.published else f"SKIP ({r.skipped_reason})"
        print(
            f"  {r.name:10s} prefixes={r.prefix_count:<6d} "
            f"asns={len(r.asns):<3d} +{len(r.added)}/-{len(r.removed)}  {status}"
        )
    print(f"Вывод: {Path(args.out).resolve()}")
    return 0


def cmd_discover(args) -> int:
    """Подсказки для курирования seed-ASN: AS-SET expansion + PeeringDB сиблинги."""
    config = load_config(args.config)
    service = config.service(args.service)
    session = make_session()

    print(f"Сервис: {service.name}")
    print(f"  seed ASN ({len(service.asns)}): {service.asns}")

    if service.as_sets:
        for as_set in service.as_sets:
            asns = irr.expand_as_set(as_set)
            print(f"  AS-SET {as_set} -> {len(asns)} ASN: {asns}")

    siblings = peeringdb.discover_siblings(session, service.asns)
    new = sorted(set(siblings) - set(service.asns))
    print(f"  PeeringDB сиблинги всего: {len(siblings)}")
    print(f"  НОВЫЕ (нет в seed, проверить вручную): {new}")
    return 0


def cmd_feed(args) -> int:
    ipv4_txt = Path(args.input)
    if not ipv4_txt.exists():
        print(f"Нет файла {ipv4_txt}. Сначала запустите `bgpcollect collect`.", file=sys.stderr)
        return 1
    paths = feed_mod.build_feed(
        ipv4_txt, Path(args.out),
        my_asn=args.asn, next_hop=args.next_hop, community=args.community,
        route_dest=args.route_dest,
    )
    for fmt, path in paths.items():
        print(f"  {fmt}: {path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bgpcollect", description=__doc__)
    p.add_argument("-c", "--config", default=DEFAULT_CONFIG, help="путь к services.yaml")
    p.add_argument("-v", "--verbose", action="store_true", help="подробный лог")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("collect", help="собрать сети и записать форматы в dist/")
    c.add_argument("-s", "--services", default="all", help="'all' или список через запятую")
    c.add_argument("-o", "--out", default=DEFAULT_OUT, help="каталог вывода")
    c.add_argument("--expand-as-sets", action="store_true", help="расширить AS-SET через IRR")
    c.add_argument("--force", action="store_true", help="игнорировать guardrail обвала")
    c.set_defaults(func=cmd_collect)

    d = sub.add_parser("discover", help="подсказки по ASN (AS-SET + PeeringDB) для курирования")
    d.add_argument("service", help="имя сервиса")
    d.set_defaults(func=cmd_discover)

    f = sub.add_parser("feed", help="сгенерировать BIRD/ExaBGP конфиг из ipv4.txt")
    f.add_argument("-i", "--input", default=f"{DEFAULT_OUT}/all/ipv4.txt", help="ipv4.txt")
    f.add_argument("-o", "--out", default="feed", help="каталог вывода")
    f.add_argument("--asn", type=int, required=True, help="ваш local ASN")
    f.add_argument("--next-hop", required=True, help="next-hop IP для анонсов")
    f.add_argument("--community", default="65432:500", help="community-тег (asn:value)")
    f.add_argument(
        "--route-dest", choices=["via", "blackhole"], default="via",
        help="via NEXT_HOP (bare-metal) или blackhole + next-hop-self (контейнер/route-server)",
    )
    f.set_defaults(func=cmd_feed)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
