import ipaddress
import json

from bgpcollect import render

NETS = [ipaddress.ip_network("8.8.8.0/24"), ipaddress.ip_network("1.1.1.0/24")]
META = {"generated_at": "2026-01-01T00:00:00+00:00", "sources": ["ripestat-ris(AS×1)"]}


def test_render_plain():
    out = render.render_plain("google", NETS, META)
    assert out == "8.8.8.0/24\n1.1.1.0/24\n"


def test_render_mikrotik():
    out = render.render_mikrotik("google", NETS, META)
    assert "/ip firewall address-list" in out
    assert "add list=google address=8.8.8.0/24" in out


def test_render_ipset():
    out = render.render_ipset("meta", NETS, META)
    assert "create meta hash:net" in out
    assert "add meta 8.8.8.0/24 -exist" in out


def test_render_wireguard():
    out = render.render_wireguard("telegram", NETS, META)
    assert "AllowedIPs = 8.8.8.0/24, 1.1.1.0/24" in out


def test_render_cisco():
    out = render.render_cisco("google", NETS, META)
    assert "ip prefix-list google permit 8.8.8.0/24" in out


def test_render_meta_json():
    out = render.render_meta("google", NETS, META)
    payload = json.loads(out)
    assert payload["service"] == "google"
    assert payload["prefix_count"] == 2
    assert payload["address_count"] == 512


def test_render_all_keys():
    out = render.render_all("google", NETS, META)
    assert set(out) >= {"ipv4.txt", "mikrotik.rsc", "nftables.conf", "meta.json"}


def test_render_wireguard_empty_is_safe():
    out = render.render_wireguard("x", [], META)
    # пустой директивы `AllowedIPs = ` быть не должно (заблокировала бы весь трафик)
    assert "AllowedIPs =" not in out
    assert "ПУСТО" in out


def test_render_nftables_empty_is_safe():
    out = render.render_nftables("x", [], META)
    assert "define" not in out
    assert "ПУСТО" in out
