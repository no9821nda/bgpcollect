"""Генерация конфигов BGP-фида (BIRD / ExaBGP) из агрегированного списка сетей.

Берёт готовый ipv4.txt (обычно dist/all/ipv4.txt) и собирает конфиг, который анонсирует
эти префиксы подписчикам с заданным community-тегом (по образцу antifilter 65432:500).
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = Path(__file__).parent / "templates"


def read_prefixes(path: Path) -> list[str]:
    """Прочитать ipv4.txt: валидные CIDR, без комментариев."""
    nets: list[ipaddress.IPv4Network] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(line, strict=False)
        except ValueError:
            continue
        if isinstance(net, ipaddress.IPv4Network):
            nets.append(net)
    return [str(n) for n in nets]


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(enabled_extensions=()),
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_bird(
    networks: list[str],
    *,
    my_asn: int,
    next_hop: str,
    community: str = "65432:500",
    include_name: str = "bgpcollect_routes.conf",
) -> str:
    comm_asn, comm_val = community.split(":", 1)
    template = _env().get_template("bird.conf.j2")
    return template.render(
        networks=networks,
        my_asn=my_asn,
        next_hop=next_hop,
        comm_asn=comm_asn,
        comm_val=comm_val,
        include_name=include_name,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def render_exabgp(
    networks: list[str],
    *,
    my_asn: int,
    router_id: str,
    next_hop: str,
    neighbor: str,
    peer_asn: int,
    community: str = "65432:500",
) -> str:
    """ExaBGP-конфиг: одна сессия, статические маршруты с community."""
    lines = [
        "# Сгенерировано bgpcollect (ExaBGP).",
        f"# Префиксов: {len(networks)}  generated_at: "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        "",
        f"neighbor {neighbor} {{",
        f"    router-id {router_id};",
        f"    local-as {my_asn};",
        f"    peer-as {peer_asn};",
        f"    local-address {router_id};",
        "    family { ipv4 unicast; }",
        "    static {",
    ]
    for net in networks:
        lines.append(
            f"        route {net} next-hop {next_hop} community [{community}];"
        )
    lines.append("    }")
    lines.append("}")
    return "\n".join(lines) + "\n"


def build_feed(
    ipv4_txt: Path,
    out_dir: Path,
    *,
    my_asn: int,
    next_hop: str,
    community: str = "65432:500",
    router_id: str | None = None,
    neighbor: str = "203.0.113.1",
    peer_asn: int = 64512,
) -> dict[str, Path]:
    """Сгенерировать bird- и exabgp-конфиги в out_dir. Вернуть {формат: путь}."""
    networks = read_prefixes(ipv4_txt)
    out_dir.mkdir(parents=True, exist_ok=True)
    router_id = router_id or next_hop

    bird_path = out_dir / "bgpcollect_routes.conf"
    bird_path.write_text(
        render_bird(networks, my_asn=my_asn, next_hop=next_hop, community=community),
        encoding="utf-8", newline="\n",
    )

    exabgp_path = out_dir / "exabgp.conf"
    exabgp_path.write_text(
        render_exabgp(
            networks, my_asn=my_asn, router_id=router_id, next_hop=next_hop,
            neighbor=neighbor, peer_asn=peer_asn, community=community,
        ),
        encoding="utf-8", newline="\n",
    )
    return {"bird": bird_path, "exabgp": exabgp_path}
