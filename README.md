# bgpcollect

Сбор IPv4-сетей сервисов (**Google, YouTube, Meta, Telegram**) из публичных данных о
маршрутизации и официальных списков, агрегация и публикация в виде готовых списков и живого
BGP-фида — по образцу [antifilter.download/#bgp_page](https://antifilter.download/#bgp_page).

## Как это работает

```
сервис → набор ASN → анонсируемые префиксы (RIPEstat/RIS)
                   ↘ официальные списки (goog.json, whois AS-SET, статические)
       → нормализация (фильтр bogon/private) → агрегация (склейка/вложенность)
       → форматы в dist/<сервис>/  +  объединённый dist/all/
       → (опц.) BGP-фид BIRD/ExaBGP с community-тегом
```

1. **Сервис → ASN.** Курируемый seed-список в [`config/services.yaml`](config/services.yaml)
   (надёжнее автоматики). Дополнительно — расширение IRR AS-SET и сверка через PeeringDB.
2. **ASN → префиксы.** RIPEstat [`announced-prefixes`](https://stat.ripe.net/docs/data-api/api-endpoints/announced-prefixes)
   — реальные анонсы из RIS (route collectors). Это основной источник.
3. **Официальные списки** (дополнение/сверка): Google `goog.json`/`cloud.json`,
   whois AS-SET для Meta (`!gAS32934` к `whois.radb.net`), статические диапазоны Telegram.
4. **Нормализация + агрегация:** только публичный IPv4, выкидываем private/bogon/слишком
   широкие, затем `collapse_addresses` (убрать вложенные, склеить смежные).
5. **Доставка:** статические списки в разных форматах + живой BGP-фид (см. [`bgp/`](bgp/)).

## Установка

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Использование

```bash
# собрать все сервисы в dist/
bgpcollect collect -s all -o dist

# отдельные сервисы + подробный лог
bgpcollect -v collect -s telegram,meta

# подсказки для курирования ASN (AS-SET expansion + PeeringDB сиблинги)
bgpcollect discover google

# сгенерировать конфиг BGP-фида из объединённого списка
bgpcollect feed -i dist/all/ipv4.txt -o feed --asn 65000 --next-hop 192.0.2.1
```

Полезные флаги `collect`: `--expand-as-sets` (раскрыть AS-SET через IRR),
`--force` (игнорировать guardrail обвала числа префиксов).

## Выходные форматы (в `dist/<сервис>/` и `dist/all/`)

| Файл | Назначение |
|---|---|
| `ipv4.txt` | голый список CIDR (для машин/скриптов) |
| `ipv4-commented.txt` | то же с шапкой-комментарием |
| `mikrotik.rsc` | MikroTik RouterOS address-list |
| `nftables.conf` | nftables named set |
| `ipset.txt` | ipset restore-формат |
| `wireguard.txt` | строка `AllowedIPs` |
| `cisco.txt` | Cisco IOS `ip prefix-list` |
| `meta.json` | статистика и метаданные запуска |

## Источники данных

| Источник | Способ | Роль |
|---|---|---|
| RIPEstat announced-prefixes | HTTP API по `AS<n>` | основной (RIS) |
| Google goog.json / cloud.json | HTTP, поле `ipv4Prefix` | официальные диапазоны |
| Meta whois AS-SET | IRRd `!gAS32934` к whois.radb.net (через сокет) | официальный prefix-list |
| Telegram статические | из конфига | стабильные известные диапазоны |
| IRR AS-SET (bgpq4-подобно) | IRRd `!i...` | опц. расширение ASN |
| PeeringDB | `org_id` → nets | обнаружение сиблинг-ASN для ревью |

> Hurricane Electric (bgp.he.net) официального API не имеет — используем как ручной ориентир
> для сверки seed-ASN; в рантайме его заменяет RIPEstat/RIS.

## Сопровождение seed-ASN

Списки ASN в `services.yaml` — это рабочий seed. Периодически проверяйте дрейф:

```bash
bgpcollect discover meta     # покажет НОВЫЕ ASN организации (нет в seed) для ручного добавления
```

AS-SET бывают избыточны, поэтому новые ASN добавляются в конфиг **руками** после проверки,
а не авто-включаются.

## Защита от «пустых» публикаций (guardrail)

`run_service` сравнивает результат с прошлым `ipv4.txt` и **не публикует**, если число
префиксов упало больше чем на `settings.max_shrink_ratio` (по умолчанию 50%) — защита от
сломанного источника, который иначе обнулил бы маршрутный фид. Обойти: `--force`.

## Автоматизация

- [`.github/workflows/update.yml`](.github/workflows/update.yml) — cron каждые 12 ч:
  тесты → `collect -s all` → коммит `dist/`.
- Для BGP-сервера — [`bgp/bgpcollect.service`](bgp/bgpcollect.service) + таймер: пересбор,
  регенерация конфига и `birdc configure`.

## Docker / docker compose

```bash
docker compose up -d --build      # collector (сбор каждые 12ч) + web (раздача)
```

- **collector** — периодически собирает сети в смонтированный `./dist`
  (интервал `COLLECT_INTERVAL`, по умолчанию 12ч; `RUN_ONCE=1` — один прогон).
- **web** — nginx раздаёт списки: **http://localhost:8080/** (antifilter-style),
  например `http://localhost:8080/all/ipv4.txt`.

Управление:

```bash
docker compose logs -f collector             # лог сборки
docker compose run --rm -e RUN_ONCE=1 collector   # разовый прогон сейчас
docker compose run --rm collector discover meta   # произвольная подкоманда CLI
docker compose --profile feed run --rm feed       # сгенерировать BGP-фид в ./feed
```

Список ASN правится в `config/services.yaml` (смонтирован в collector только для чтения —
пересборка образа не нужна). Контейнер работает от root, чтобы без трения писать в bind-mount
`./dist`. Параметры фида (`--asn/--next-hop/--community`) задаются в сервисе `feed`
в [`docker-compose.yml`](docker-compose.yml).

## Тесты

```bash
pytest -q                                  # офлайн юнит-тесты
BGPCOLLECT_NETWORK_TESTS=1 pytest -q        # + сетевой smoke (telegram)
```

## Структура

```
config/services.yaml      сервис → ASN, AS-SET, официальные источники, статические сети
src/bgpcollect/
  config.py               загрузка/валидация конфига
  http.py                 requests-сессия с ретраями
  sources/ripestat.py     announced-prefixes (RIS) — основной
  sources/official.py     goog.json, whois IRRd (сокет)
  sources/irr.py          расширение AS-SET
  sources/peeringdb.py    обнаружение сиблинг-ASN
  aggregate.py            нормализация + collapse_addresses
  render.py               рендереры форматов
  pipeline.py             оркестрация + дифф + guardrail
  feed.py                 генерация BIRD/ExaBGP
  cli.py                  CLI
bgp/                      ops: systemd unit, README про BGP-доставку
Dockerfile                образ сборщика
docker-compose.yml        collector + web (+ опц. профиль feed)
docker/                   entrypoint.sh, nginx.conf
dist/                     публикуемые списки (артефакт)
tests/                    юнит + сетевой smoke
```
