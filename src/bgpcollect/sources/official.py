"""Официальные/публичные источники для сверки и дополнения BGP-данных.

  * google_json  — gstatic goog.json / cloud.json (поле ipv4Prefix);
  * whois_asset  — IRRd-запрос (например `!gAS32934`) к whois.radb.net через сокет
                   (не требует системного бинаря whois, работает и на Windows).
"""

from __future__ import annotations

import logging
import socket

import requests

from ..config import OfficialSource

log = logging.getLogger(__name__)


def fetch_google_json(session: requests.Session, url: str, *, timeout: int = 30) -> list[str]:
    """Достать ipv4Prefix из gstatic goog.json / cloud.json."""
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    prefixes = [
        entry["ipv4Prefix"]
        for entry in payload.get("prefixes", [])
        if entry.get("ipv4Prefix")
    ]
    log.info("%s: %d ipv4Prefix", url, len(prefixes))
    return prefixes


def _recv_line(sock: socket.socket) -> bytes:
    data = bytearray()
    while not data.endswith(b"\n"):
        chunk = sock.recv(1)
        if not chunk:
            break
        data += chunk
    return bytes(data)


def query_irrd(server: str, query: str, *, port: int = 43, timeout: int = 30) -> list[str]:
    """Выполнить IRRd-запрос (`!g...`/`!i...`) и вернуть список токенов-префиксов.

    Протокол IRRd: ответ начинается со строки `A<n>` (далее n байт payload),
    затем строка-статус (`C` успех / `D` нет данных / `F <reason>` ошибка).
    """
    with socket.create_connection((server, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(b"!!\n")  # persistent mode
        sock.sendall((query + "\n").encode())

        header = _recv_line(sock).decode(errors="replace").strip()
        prefixes: list[str] = []
        if header.startswith("A"):
            try:
                nbytes = int(header[1:])
            except ValueError:
                nbytes = 0
            payload = bytearray()
            while len(payload) < nbytes:
                chunk = sock.recv(nbytes - len(payload))
                if not chunk:
                    break
                payload += chunk
            _recv_line(sock)  # завершающая строка-статус
            prefixes = payload.decode(errors="replace").split()
        elif header.startswith("D"):
            log.warning("IRRd %s: ключ не найден для запроса %r", server, query)
        elif header.startswith("F"):
            log.error("IRRd %s: ошибка для запроса %r: %s", server, query, header)

        try:
            sock.sendall(b"!q\n")
        except OSError:
            pass
        log.info("IRRd %s %r: %d префиксов", server, query, len(prefixes))
        return prefixes


def fetch_official(session: requests.Session, source: OfficialSource, *, timeout: int = 30) -> list[str]:
    """Диспетчер по типу официального источника. Ошибки логируем, возвращаем []."""
    try:
        if source.type == "google_json":
            return fetch_google_json(session, source.url, timeout=timeout)
        if source.type == "whois_asset":
            return query_irrd(source.server, source.query, timeout=timeout)
    except (requests.RequestException, OSError, ValueError) as exc:
        log.error("Источник %s упал: %s", source.type, exc)
    return []
