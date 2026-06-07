from bgpcollect import aggregate
from bgpcollect.sources import domains as domain_src
from bgpcollect.sources import lists as list_src


def test_read_list_file_parses(tmp_path):
    f = tmp_path / "custom.txt"
    f.write_text(
        "\n".join(
            [
                "# комментарий",
                "203.0.113.0/24",
                "198.51.100.7   # одиночный IP",
                "",
                "8.8.8.0/24, 1.1.1.0/24",   # несколько в строке
                "   ",
            ]
        ),
        encoding="utf-8",
    )
    tokens = list_src.read_list_file(f)
    assert tokens == ["203.0.113.0/24", "198.51.100.7", "8.8.8.0/24", "1.1.1.0/24"]


def test_read_list_file_missing(tmp_path):
    assert list_src.read_list_file(tmp_path / "nope.txt") == []


def test_read_list_then_aggregate_makes_host_routes_32(tmp_path):
    f = tmp_path / "ips.txt"
    f.write_text("8.8.8.8\n8.8.4.4\n", encoding="utf-8")
    nets = aggregate.aggregate(list_src.read_list_file(f), min_prefixlen=8)
    assert {str(n) for n in nets} == {"8.8.8.8/32", "8.8.4.4/32"}


def test_resolve_domains_mocked(monkeypatch):
    def fake_getaddrinfo(name, *a, **k):
        table = {
            "a.example": [(0, 0, 0, "", ("8.8.8.8", 0)), (0, 0, 0, "", ("8.8.4.4", 0))],
            "b.example": [(0, 0, 0, "", ("1.1.1.1", 0))],
        }
        return table[name]

    monkeypatch.setattr(domain_src.socket, "getaddrinfo", fake_getaddrinfo)
    assert domain_src.resolve_domains(["a.example", "b.example"]) == ["1.1.1.1", "8.8.4.4", "8.8.8.8"]


def test_resolve_domains_handles_failure(monkeypatch):
    def boom(name, *a, **k):
        raise OSError("no such host")

    monkeypatch.setattr(domain_src.socket, "getaddrinfo", boom)
    assert domain_src.resolve_domains(["bad.example"]) == []
