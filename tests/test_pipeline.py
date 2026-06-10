"""Тесты оркестрации: guardrail + fallback в dist/all, атомарная запись.

Сервисы в тестовых конфигах используют только static_prefixes — сеть не нужна.
"""

import json

from bgpcollect.config import load_config
from bgpcollect.pipeline import run_all
from bgpcollect.util import atomic_write


def _config(tmp_path, yaml_text):
    p = tmp_path / "services.yaml"
    p.write_text(yaml_text, encoding="utf-8")
    return load_config(p)


def test_run_all_keeps_previous_prefixes_for_skipped_service(tmp_path):
    """SKIP-нутый guardrail'ом сервис не должен выпадать из dist/all (HIGH-1)."""
    cfg = _config(
        tmp_path,
        # свежий сбор даст 1 префикс
        "services:\n  svc:\n    static_prefixes: [8.8.8.0/24]\n",
    )
    out = tmp_path / "dist"
    # «предыдущий» опубликованный список — 10 префиксов => 1/10 < 50% => guardrail SKIP
    prev = [f"9.9.{i}.0/24" for i in range(10)]
    (out / "svc").mkdir(parents=True)
    (out / "svc" / "ipv4.txt").write_text("\n".join(prev) + "\n", encoding="utf-8")

    results = run_all(cfg, ["svc"], session=None, out_dir=out)

    assert results[0].published is False  # guardrail сработал
    # per-service список НЕ перезаписан
    svc_lines = (out / "svc" / "ipv4.txt").read_text(encoding="utf-8").split()
    assert svc_lines == prev
    # объединённый all/ содержит СТАРЫЕ префиксы сервиса (агрегированные), а не пустоту
    import ipaddress
    all_nets = [
        ipaddress.ip_network(l)
        for l in (out / "all" / "ipv4.txt").read_text(encoding="utf-8").split()
    ]
    expected = list(ipaddress.collapse_addresses(ipaddress.ip_network(p) for p in prev))
    assert all_nets == expected
    meta = json.loads((out / "all" / "meta.json").read_text(encoding="utf-8"))
    assert meta["stale_services"] == ["svc"]
    assert meta["services"] == []


def test_run_all_publishes_fresh_and_combined(tmp_path):
    cfg = _config(
        tmp_path,
        "services:\n"
        "  a:\n    static_prefixes: [8.8.8.0/24]\n"
        "  b:\n    static_prefixes: [9.9.9.0/24]\n",
    )
    out = tmp_path / "dist"
    results = run_all(cfg, ["a", "b"], session=None, out_dir=out)
    assert all(r.published for r in results)
    all_lines = set((out / "all" / "ipv4.txt").read_text(encoding="utf-8").split())
    assert all_lines == {"8.8.8.0/24", "9.9.9.0/24"}
    meta = json.loads((out / "all" / "meta.json").read_text(encoding="utf-8"))
    assert meta["stale_services"] == []


def test_run_all_force_overrides_guardrail(tmp_path):
    cfg = _config(tmp_path, "services:\n  svc:\n    static_prefixes: [8.8.8.0/24]\n")
    out = tmp_path / "dist"
    (out / "svc").mkdir(parents=True)
    (out / "svc" / "ipv4.txt").write_text(
        "\n".join(f"9.9.{i}.0/24" for i in range(10)) + "\n", encoding="utf-8"
    )
    results = run_all(cfg, ["svc"], session=None, out_dir=out, force=True)
    assert results[0].published is True
    assert (out / "svc" / "ipv4.txt").read_text(encoding="utf-8").split() == ["8.8.8.0/24"]


def test_atomic_write_creates_and_replaces(tmp_path):
    target = tmp_path / "sub" / "f.txt"
    atomic_write(target, "v1\n")
    assert target.read_text(encoding="utf-8") == "v1\n"
    atomic_write(target, "v2\n")
    assert target.read_text(encoding="utf-8") == "v2\n"
    # tmp-файлов не осталось
    leftovers = [p for p in target.parent.iterdir() if p.name != "f.txt"]
    assert leftovers == []
