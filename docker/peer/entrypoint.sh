#!/bin/sh
# Демо-подписчик: устанавливает BGP-сессию к фиду и принимает (import all) его маршруты.
# Проверка: birdc -s /run/bird/bird.ctl show route [all]
#
# Переменные окружения:
#   FEED_IP    адрес фида (по умолч. 172.31.0.10)
#   FEED_ASN   ASN фида (по умолч. 65000)
#   PEER_ASN   собственный ASN (по умолч. 64512)
#   ROUTER_ID  router id (по умолч. 172.31.0.20)
set -eu

FEED_IP="${FEED_IP:-172.31.0.10}"
FEED_ASN="${FEED_ASN:-65000}"
PEER_ASN="${PEER_ASN:-64512}"
ROUTER_ID="${ROUTER_ID:-172.31.0.20}"
SOCK="/run/bird/bird.ctl"

mkdir -p /run/bird

cat > /run/bird/peer.conf <<EOF
log stderr all;
router id $ROUTER_ID;

protocol device { }

protocol bgp feed {
    local as $PEER_ASN;
    neighbor $FEED_IP as $FEED_ASN;
    ipv4 {
        import all;       # учим всё, что отдаёт фид
        export none;
    };
}
EOF

bird -p -c /run/bird/peer.conf
echo "[peer] подключаюсь к фиду $FEED_IP as $FEED_ASN (local as $PEER_ASN)"
exec bird -f -c /run/bird/peer.conf -s "$SOCK"
