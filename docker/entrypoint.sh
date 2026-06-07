#!/bin/sh
# Entrypoint сборщика: один прогон, либо периодический цикл.
#
# Переменные окружения:
#   SERVICES          'all' или список через запятую (по умолч. all)
#   OUT_DIR           каталог вывода (по умолч. /app/dist)
#   COLLECT_INTERVAL  пауза между прогонами в секундах (по умолч. 43200 = 12ч)
#   RUN_ONCE          1 — выполнить один раз и выйти (для cron/CI)
#   VERBOSE           1 — подробный лог
#   EXTRA_ARGS        доп. аргументы для `collect` (например: --expand-as-sets)
#   FEED_ENABLED      1 — после сбора генерировать BIRD routes (blackhole) в FEED_OUT
#   FEED_OUT          каталог для bgpcollect_routes.conf (по умолч. /app/feed)
#   FEED_ASN          local ASN фида (по умолч. 65000)
#   FEED_NEXT_HOP     next-hop (для совместимости; в blackhole не используется)
#   FEED_COMMUNITY    community-тег (по умолч. 65432:500)
set -eu

SERVICES="${SERVICES:-all}"
OUT_DIR="${OUT_DIR:-/app/dist}"
COLLECT_INTERVAL="${COLLECT_INTERVAL:-43200}"
RUN_ONCE="${RUN_ONCE:-0}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

FEED_ENABLED="${FEED_ENABLED:-0}"
FEED_OUT="${FEED_OUT:-/app/feed}"
FEED_ASN="${FEED_ASN:-65000}"
FEED_NEXT_HOP="${FEED_NEXT_HOP:-192.0.2.1}"
FEED_COMMUNITY="${FEED_COMMUNITY:-65432:500}"

verbose_flag=""
[ "${VERBOSE:-0}" = "1" ] && verbose_flag="-v"

# Если переданы аргументы (docker run ... discover meta) — выполнить их и выйти.
if [ "$#" -gt 0 ]; then
    exec python -m bgpcollect $verbose_flag "$@"
fi

generate_feed() {
    [ "$FEED_ENABLED" = "1" ] || return 0
    ipv4="$OUT_DIR/all/ipv4.txt"
    if [ ! -s "$ipv4" ]; then
        echo "[entrypoint] feed: нет $ipv4 — пропускаю генерацию"
        return 0
    fi
    echo "[entrypoint] feed: BIRD routes (blackhole) -> $FEED_OUT (asn=$FEED_ASN comm=$FEED_COMMUNITY)"
    python -m bgpcollect $verbose_flag feed -i "$ipv4" -o "$FEED_OUT" \
        --asn "$FEED_ASN" --next-hop "$FEED_NEXT_HOP" --community "$FEED_COMMUNITY" \
        --route-dest blackhole \
        || echo "[entrypoint] feed: генерация упала (продолжаем)"
}

run_once() {
    echo "[entrypoint] collect services=$SERVICES out=$OUT_DIR"
    # не валим контейнер, если упал один источник
    python -m bgpcollect $verbose_flag collect -s "$SERVICES" -o "$OUT_DIR" $EXTRA_ARGS \
        || echo "[entrypoint] collect завершился с ошибкой (продолжаем)"
    generate_feed
}

run_once

if [ "$RUN_ONCE" = "1" ]; then
    echo "[entrypoint] RUN_ONCE=1 — выход"
    exit 0
fi

while true; do
    echo "[entrypoint] сон ${COLLECT_INTERVAL}s до следующего прогона"
    sleep "$COLLECT_INTERVAL"
    run_once
done
