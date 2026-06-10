import pytest

from bgpcollect import feed
from bgpcollect.config import load_config

CONFIG_YAML = """
settings:
  min_ipv4_prefixlen: 8
services:
  google:
    asns: [15169, 36040]
    official:
      - {type: google_json, url: "https://example.test/goog.json"}
  youtube:
    asns: [43515]
  telegram:
    asns: [62041]
    static_prefixes: [91.108.0.0/16]
"""


def _write(tmp_path, text):
    p = tmp_path / "services.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_load_config_parses(tmp_path):
    cfg = load_config(_write(tmp_path, CONFIG_YAML))
    assert set(cfg.services) == {"google", "youtube", "telegram"}
    assert cfg.services["google"].asns == [15169, 36040]
    assert cfg.services["google"].official[0].type == "google_json"
    assert cfg.services["telegram"].static_prefixes == ["91.108.0.0/16"]


def test_load_config_parses_exclude(tmp_path):
    text = """
services:
  google:
    asns: [15169]
    official:
      - {type: google_json, url: "https://x/goog.json"}
    exclude:
      official:
        - {type: google_json, url: "https://x/cloud.json"}
      asns: [396982]
  bare:
    asns: [1]
"""
    cfg = load_config(_write(tmp_path, text))
    g = cfg.services["google"]
    assert g.exclude.asns == [396982]
    assert g.exclude.official[0].url.endswith("cloud.json")
    assert not g.exclude.is_empty()
    # сервис без exclude -> пустой набор
    assert cfg.services["bare"].exclude.is_empty()


def test_load_config_unknown_settings_key(tmp_path):
    bad = "settings:\n  min_ipv4_prefixlen: 8\n  typo_key: 1\nservices:\n  x:\n    asns: [1]\n"
    with pytest.raises(ValueError, match="typo_key"):
        load_config(_write(tmp_path, bad))


def test_service_unknown_raises(tmp_path):
    cfg = load_config(_write(tmp_path, CONFIG_YAML))
    with pytest.raises(KeyError):
        cfg.service("nonexistent")


def test_render_bird_has_routes_and_community():
    out = feed.render_bird(
        ["91.108.0.0/16", "149.154.160.0/20"],
        my_asn=65000, next_hop="192.0.2.1", community="65432:500",
    )
    assert "route 91.108.0.0/16 via BGPCOLLECT_NEXT_HOP;" in out
    assert "BGPCOLLECT_COMM = (65432, 500);" in out


def test_render_bird_blackhole_mode():
    out = feed.render_bird(
        ["91.108.0.0/16", "149.154.160.0/20"],
        my_asn=65000, next_hop="192.0.2.1", community="65432:500",
        route_dest="blackhole",
    )
    assert "route 91.108.0.0/16 blackhole;" in out
    assert "via BGPCOLLECT_NEXT_HOP" not in out          # next-hop не используется
    assert "BGPCOLLECT_NEXT_HOP" not in out               # define отсутствует
    assert "next hop self" in out                         # подсказка в примере сессии
    assert "BGPCOLLECT_COMM = (65432, 500);" in out


def test_render_bird_rejects_bad_route_dest():
    import pytest
    with pytest.raises(ValueError):
        feed.render_bird(["91.108.0.0/16"], my_asn=1, next_hop="192.0.2.1", route_dest="oops")


def test_render_exabgp_has_community():
    out = feed.render_exabgp(
        ["91.108.0.0/16"],
        my_asn=65000, router_id="192.0.2.1", next_hop="192.0.2.1",
        neighbor="203.0.113.1", peer_asn=64512, community="65432:500",
    )
    assert "route 91.108.0.0/16 next-hop 192.0.2.1 community [65432:500];" in out
