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
set -eu

SERVICES="${SERVICES:-all}"
OUT_DIR="${OUT_DIR:-/app/dist}"
COLLECT_INTERVAL="${COLLECT_INTERVAL:-43200}"
RUN_ONCE="${RUN_ONCE:-0}"
EXTRA_ARGS="${EXTRA_ARGS:-}"

verbose_flag=""
[ "${VERBOSE:-0}" = "1" ] && verbose_flag="-v"

# Если переданы аргументы (docker run ... discover meta) — выполнить их и выйти.
if [ "$#" -gt 0 ]; then
    exec python -m bgpcollect $verbose_flag "$@"
fi

run_once() {
    echo "[entrypoint] collect services=$SERVICES out=$OUT_DIR"
    # не валим контейнер, если упал один источник
    python -m bgpcollect $verbose_flag collect -s "$SERVICES" -o "$OUT_DIR" $EXTRA_ARGS \
        || echo "[entrypoint] collect завершился с ошибкой (продолжаем)"
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
