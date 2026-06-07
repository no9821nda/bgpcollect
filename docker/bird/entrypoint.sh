#!/bin/sh
# Entrypoint BGP-фида: готовит конфиг, запускает BIRD и перечитывает маршруты при обновлении.
#
# Переменные окружения:
#   FEED_ASN              local ASN фида (по умолч. 65000)
#   ROUTER_ID             router id (по умолч. 10.255.255.1; в demo — статический IP)
#   FEED_COMMUNITY        community для stub'а, пока нет реального файла (по умолч. 65432:500)
#   BIRD_RELOAD_INTERVAL  период проверки обновления маршрутов, сек (по умолч. 30)
#   PEER_IP / PEER_ASN    опциональный одиночный пир (явная сессия)
set -eu

FEED_ASN="${FEED_ASN:-65000}"
ROUTER_ID="${ROUTER_ID:-10.255.255.1}"
FEED_COMMUNITY="${FEED_COMMUNITY:-65432:500}"
RELOAD_INTERVAL="${BIRD_RELOAD_INTERVAL:-30}"
SRC_ROUTES="/etc/bird/feed/bgpcollect_routes.conf"   # из общего тома ./feed (ro)
RUN_ROUTES="/run/bird/bgpcollect_routes.conf"        # включается из bird.conf
SOCK="/run/bird/bird.ctl"

mkdir -p /run/bird

echo "router id $ROUTER_ID;" > /run/bird/local.conf

write_stub() {
    ca="${FEED_COMMUNITY%%:*}"; cv="${FEED_COMMUNITY##*:}"
    {
        echo "define BGPCOLLECT_COMM = ($ca, $cv);"
        echo "protocol static bgpcollect { ipv4; }"
        echo "filter bgpcollect_export {"
        echo "    if proto = \"bgpcollect\" then { bgp_community.add(BGPCOLLECT_COMM); accept; }"
        echo "    reject;"
        echo "}"
    } > "$RUN_ROUTES"
}

if [ -s "$SRC_ROUTES" ]; then
    cp "$SRC_ROUTES" "$RUN_ROUTES"
else
    echo "[bird] $SRC_ROUTES отсутствует — пишу stub (фид пуст, пока collector не сгенерирует)"
    write_stub
fi

# Опциональный одиночный пир из env.
if [ -n "${PEER_IP:-}" ]; then
    PEER_ASN="${PEER_ASN:-64512}"
    {
        echo "protocol bgp env_peer {"
        echo "    local as $FEED_ASN;"
        echo "    neighbor $PEER_IP as $PEER_ASN;"
        echo "    ipv4 {"
        echo "        import none;"
        echo "        export filter bgpcollect_export;"
        echo "        next hop self;"
        echo "    };"
        echo "}"
    } > /run/bird/peer.env.conf
    echo "[bird] env-пир: neighbor $PEER_IP as $PEER_ASN"
else
    : > /run/bird/peer.env.conf
fi

# Проверка конфига до запуска (упадём с понятной ошибкой, если что-то не так).
bird -p -c /etc/bird/bird.conf
echo "[bird] конфиг валиден; запуск (router id $ROUTER_ID, local as $FEED_ASN)"

bird -f -c /etc/bird/bird.conf -s "$SOCK" &
BIRD_PID=$!
trap 'kill "$BIRD_PID" 2>/dev/null || true' TERM INT

# Reloader: при изменении исходного routes-файла копируем и делаем `configure` (без дропа сессий).
sum_of() { if [ -s "$1" ]; then md5sum "$1" | awk '{print $1}'; else echo ""; fi; }
last="$(sum_of "$SRC_ROUTES")"
while kill -0 "$BIRD_PID" 2>/dev/null; do
    sleep "$RELOAD_INTERVAL"
    cur="$(sum_of "$SRC_ROUTES")"
    if [ -n "$cur" ] && [ "$cur" != "$last" ]; then
        echo "[bird] маршруты обновились — birdc configure"
        cp "$SRC_ROUTES" "$RUN_ROUTES"
        birdc -s "$SOCK" configure || echo "[bird] configure упал"
        last="$cur"
    fi
done
wait "$BIRD_PID"
