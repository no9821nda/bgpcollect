"""Сетевой smoke-тест (opt-in): запускается только при BGPCOLLECT_NETWORK_TESTS=1.

Проверяет, что реальный конвейер для telegram отдаёт непустой осмысленный результат.
"""

import os
from pathlib import Path

import pytest

from bgpcollect.config import load_config
from bgpcollect.http import make_session
from bgpcollect.pipeline import collect_service

pytestmark = pytest.mark.skipif(
    os.environ.get("BGPCOLLECT_NETWORK_TESTS") != "1",
    reason="сетевой тест; установите BGPCOLLECT_NETWORK_TESTS=1",
)

CONFIG = Path(__file__).resolve().parents[1] / "config" / "services.yaml"


def test_telegram_smoke():
    cfg = load_config(CONFIG)
    networks, sources, raw, asns = collect_service(
        cfg, cfg.service("telegram"), make_session()
    )
    nets = {str(n) for n in networks}
    # известный стабильный диапазон Telegram должен присутствовать (статический + RIS)
    assert any(n.startswith("91.108.") for n in nets)
    assert len(networks) >= 3
    assert "static" in sources
