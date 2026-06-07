# bgpcollect — образ сборщика IPv4-сетей сервисов.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Устанавливаем пакет (слой кешируется, пока не меняются исходники/метаданные).
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

# Конфиг по умолчанию и entrypoint.
COPY config ./config
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh \
    && mkdir -p /app/dist /app/feed

# Работаем от root, чтобы без трения писать в bind-mount'ы ./dist и ./feed
# (для self-hosted утилиты это приемлемо; при желании добавьте USER и согласуйте uid с хостом).

# Значения по умолчанию (переопределяются в docker-compose / docker run -e ...).
ENV SERVICES=all \
    OUT_DIR=/app/dist \
    COLLECT_INTERVAL=43200 \
    RUN_ONCE=0 \
    VERBOSE=1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
