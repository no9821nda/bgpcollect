import responses

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


def test_irr_as_regex_parsing(monkeypatch):
    # подменяем сетевой запрос на фиктивный ответ IRRd
    monkeypatch.setattr(
        irr, "query_irrd", lambda *a, **k: ["AS32934", "AS54115", "junk", "as63293"]
    )
    asns = irr.expand_as_set("AS-FACEBOOK")
    assert asns == [32934, 54115, 63293]
