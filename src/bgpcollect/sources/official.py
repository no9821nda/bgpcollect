"""Официальные/публичные источники для сверки и дополнения BGP-данных.

  * google_json  — gstatic goog.json / cloud.json (поле ipv4Prefix);
  * whois_asset  — IRRd-запрос (например `!gAS32934`) к whois.radb.net через сокет
                   (не требует системного бинаря whois, работает и на Windows);
  * cidr_list    — простой текстовый список CIDR/IP по HTTP (по одному в строке,
                   напр. https://core.telegram.org/resources/cidr.txt). IPv6/мусор
                   отсеются позже в aggregate.normalize.
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


def fetch_cidr_list(session: requests.Session, url: str, *, timeout: int = 30) -> list[str]:
    """Достать токены CIDR/IP из простого текстового списка (по одному в строке).

    Срезаем inline-комментарии (`#`), пустые строки; поддерживаем несколько токенов
    в строке (через пробел или запятую). Валидация — в aggregate.normalize.
    """
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    tokens: list[str] = []
    for line in resp.text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tokens.extend(line.replace(",", " ").split())
    log.info("%s: %d записей", url, len(tokens))
    return tokens


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
        if source.type == "cidr_list":
            return fetch_cidr_list(session, source.url, timeout=timeout)
    except (requests.RequestException, OSError, ValueError) as exc:
        log.error("Источник %s упал: %s", source.type, exc)
    return []
