"""Общий HTTP-клиент: сессия с ретраями и вежливым User-Agent."""

from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from . import __version__

DEFAULT_TIMEOUT = 30
USER_AGENT = f"bgpcollect/{__version__} (+https://github.com/; routing data collector)"


def make_session(total_retries: int = 4, backoff: float = 1.0) -> requests.Session:
    """Сессия requests с экспоненциальными ретраями на сетевые/5xx/429 ошибки."""
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": USER_AGENT})
    return session
