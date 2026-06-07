import ipaddress

from bgpcollect import aggregate


def net(s):
    return ipaddress.ip_network(s)


def test_parse_ipv4_valid():
    assert aggregate.parse_ipv4("8.8.8.0/24") == net("8.8.8.0/24")
    assert aggregate.parse_ipv4(" 1.2.3.0/24 ") == net("1.2.3.0/24")


def test_parse_ipv4_rejects_ipv6_and_garbage():
    assert aggregate.parse_ipv4("2001:4860::/32") is None
    assert aggregate.parse_ipv4("not-a-prefix") is None
    assert aggregate.parse_ipv4("") is None


def test_parse_ipv4_non_strict_host_bits():
    # хостовые биты не должны ломать парсинг
    assert aggregate.parse_ipv4("8.8.8.8/24") == net("8.8.8.0/24")


def test_is_acceptable_filters():
    assert aggregate.is_acceptable(net("8.8.8.0/24"), 8)
    assert not aggregate.is_acceptable(net("10.0.0.0/8"), 8)       # private
    assert not aggregate.is_acceptable(net("192.168.0.0/16"), 8)   # private
    assert not aggregate.is_acceptable(net("127.0.0.0/8"), 8)      # loopback
    assert not aggregate.is_acceptable(net("224.0.0.0/4"), 8)      # multicast
    assert not aggregate.is_acceptable(net("240.0.0.0/4"), 8)      # reserved
    assert not aggregate.is_acceptable(net("0.0.0.0/0"), 8)        # default/too broad
    assert not aggregate.is_acceptable(net("2.0.0.0/7"), 8)        # короче min_prefixlen


def test_normalize_dedup_and_filter():
    out = aggregate.normalize(
        ["8.8.8.0/24", "8.8.8.0/24", "10.0.0.0/8", "2001:4860::/32", "garbage"],
        min_prefixlen=8,
    )
    assert out == [net("8.8.8.0/24")]


def test_merge_adjacent_and_nested():
    # merge не фильтрует — только склейка/вложенность
    merged = aggregate.merge([net("8.8.8.0/24"), net("8.8.9.0/24")])
    assert merged == [net("8.8.8.0/23")]

    merged2 = aggregate.merge([net("10.0.0.0/8"), net("10.1.2.0/24")])
    assert merged2 == [net("10.0.0.0/8")]  # вложенный поглощён


def test_aggregate_end_to_end():
    # используем заведомо публичные адреса (8.8.0.0/16 — Google),
    # чтобы не зависеть от классификации спец-диапазонов в разных патчах Python
    result = aggregate.aggregate(
        ["8.8.8.0/24", "8.8.9.0/24", "10.0.0.0/8"], min_prefixlen=8
    )
    # private (10/8) отфильтрован, два смежных /24 склеены в /23
    assert result == [net("8.8.8.0/23")]


def test_count_addresses():
    assert aggregate.count_addresses([net("8.8.8.0/24")]) == 256


def test_subtract_carves_out_inner():
    # из /22 вычитаем один /24 -> остаются три /24
    result = aggregate.subtract([net("8.8.8.0/22")], [net("8.8.9.0/24")])
    assert set(result) == {net("8.8.8.0/24"), net("8.8.10.0/23")}


def test_subtract_drops_fully_covered():
    result = aggregate.subtract([net("8.8.8.0/24")], [net("8.8.0.0/16")])
    assert result == []


def test_subtract_keeps_disjoint():
    result = aggregate.subtract([net("8.8.8.0/24")], [net("1.1.1.0/24")])
    assert result == [net("8.8.8.0/24")]


def test_subtract_no_excludes_returns_merged():
    result = aggregate.subtract([net("8.8.8.0/24"), net("8.8.9.0/24")], [])
    assert result == [net("8.8.8.0/23")]
