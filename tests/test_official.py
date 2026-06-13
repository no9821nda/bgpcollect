import responses

from bgpcollect import aggregate
from bgpcollect.config import OfficialSource
from bgpcollect.http import make_session
from bgpcollect.sources import irr, official


@responses.activate
def test_fetch_google_json_extracts_ipv4_only():
    url = "https://www.gstatic.com/ipranges/goog.json"
    responses.add(
        responses.GET,
        url,
        json={
            "prefixes": [
                {"ipv4Prefix": "8.8.4.0/24"},
                {"ipv6Prefix": "2001:4860::/32"},
                {"ipv4Prefix": "8.8.8.0/24"},
            ]
        },
        status=200,
    )
    out = official.fetch_google_json(make_session(), url)
    assert out == ["8.8.4.0/24", "8.8.8.0/24"]


CIDR_TXT = """\
# Telegram ranges
91.108.4.0/22
91.108.8.0/22

2001:67c:4e8::/48
91.105.192.0/23  # inline comment
"""


@responses.activate
def test_fetch_cidr_list_returns_raw_tokens():
    url = "https://core.telegram.org/resources/cidr.txt"
    responses.add(responses.GET, url, body=CIDR_TXT, status=200)
    out = official.fetch_cidr_list(make_session(), url)
    # сырые токены: комментарии/пустые строки убраны, IPv6 пока остаётся
    assert out == ["91.108.4.0/22", "91.108.8.0/22", "2001:67c:4e8::/48", "91.105.192.0/23"]


@responses.activate
def test_fetch_cidr_list_via_dispatcher_then_normalize_drops_ipv6():
    url = "https://core.telegram.org/resources/cidr.txt"
    responses.add(responses.GET, url, body=CIDR_TXT, status=200)
    raw = official.fetch_official(make_session(), OfficialSource(type="cidr_list", url=url))
    nets = aggregate.aggregate(raw)
    assert [str(n) for n in nets] == ["91.105.192.0/23", "91.108.4.0/22", "91.108.8.0/22"]


def test_irr_as_regex_parsing(monkeypatch):
    # подменяем сетевой запрос на фиктивный ответ IRRd
    monkeypatch.setattr(
        irr, "query_irrd", lambda *a, **k: ["AS32934", "AS54115", "junk", "as63293"]
    )
    asns = irr.expand_as_set("AS-FACEBOOK")
    assert asns == [32934, 54115, 63293]
