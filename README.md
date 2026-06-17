# bgpcollect

Сбор IPv4-сетей сервисов (**Google, YouTube, Meta, Telegram, Claude, OpenAI, Gemini**) из публичных данных о
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

## Прямые ссылки на списки

Готовые `ipv4.txt` публикуются в `dist/` и доступны напрямую через `raw.githubusercontent.com`
(ветка `main`):

| Сервис | Прямая ссылка |
|---|---|
| Все (all) | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/all/ipv4.txt |
| Google | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/google/ipv4.txt |
| Meta | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/meta/ipv4.txt |
| Telegram | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/telegram/ipv4.txt |
| YouTube | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/youtube/ipv4.txt |
| Claude | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/claude/ipv4.txt |
| OpenAI | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/openai/ipv4.txt |
| Gemini | https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/gemini/ipv4.txt |

Формат: `https://raw.githubusercontent.com/no9821nda/bgpcollect/main/dist/<сервис>/ipv4.txt`.
Другие форматы (`mikrotik.rsc`, `nftables.conf`, `ipset.txt`, …) лежат рядом в той же папке.

> `raw.githubusercontent.com` кэшируется CDN (~5 мин), так что свежие обновления подтянутся
> с небольшой задержкой.

## Источники данных

| Источник | Способ | Роль |
|---|---|---|
| RIPEstat announced-prefixes | HTTP API по `AS<n>` | основной (RIS) |
| Google goog.json / cloud.json | HTTP, поле `ipv4Prefix` | официальные диапазоны |
| Meta whois AS-SET | IRRd `!gAS32934` к whois.radb.net (через сокет) | официальный prefix-list |
| Telegram статические | из конфига | стабильные известные диапазоны |
| IRR AS-SET (bgpq4-подобно) | IRRd `!i...` | опц. расширение ASN |
| PeeringDB | `org_id` → nets | обнаружение сиблинг-ASN для ревью |
| **Свой файл-список** | `lists:` → файл CIDR/IP | ваши произвольные списки |
| **Домены** | `domains:` → A-записи | резолв доменов в IPv4 |

> Hurricane Electric (bgp.he.net) официального API не имеет — используем как ручной ориентир
> для сверки seed-ASN; в рантайме его заменяет RIPEstat/RIS.

### Свои списки IP

Любой сервис в [`config/services.yaml`](config/services.yaml) комбинирует источники
`asns` / `static_prefixes` / `lists` / `domains`:

```yaml
services:
  custom:
    description: Мой список
    static_prefixes: [203.0.113.0/24, 198.51.100.7]   # инлайн (IP без маски → /32)
    lists: [lists/custom.txt]                          # файл: по одному CIDR/IP в строке, # — комментарий
    domains: [example.com, api.example.com]            # резолв в A-записи
```

- Файлы-списки лежат в [`lists/`](lists/); путь — относительно запуска (в Docker — `/app`,
  каталог монтируется как `./lists:/app/lists:ro`).
- Все источники проходят общий фильтр: bogon/private/документационные (RFC 5737) диапазоны
  отбрасываются, остальное агрегируется.
- `domains` даёт лишь те IP, что вернул резолвер в момент запуска — для CDN это нестабильно
  и неполно; для надёжного покрытия используйте `asns`.

### Исключение диапазонов (`exclude`)

`exclude:` вычитает указанные подсети из результата сервиса (set-difference по CIDR — режет
и пересчитывает префиксы). Принимает те же источники, что и сбор (`asns/official/static_prefixes/
lists/domains`). Так из Google убран **Google Cloud (GCP)**:

```yaml
google:
  asns: [15169, ...]                       # без AS396982 (GOOGLE-CLOUD-PLATFORM)
  official:
    - {type: google_json, url: "https://www.gstatic.com/ipranges/goog.json"}   # все диапазоны Google
  exclude:
    official:
      - {type: google_json, url: "https://www.gstatic.com/ipranges/cloud.json"} # вычесть GCP
    asns: [396982]
```

Результат = `goog.json − cloud.json` (как рекомендует Google для «только сервисы Google»).
На практике это срезало Google с ~640 до ~178 префиксов; `8.8.8.0/24` (Google DNS) остаётся,
GCP-диапазоны (34.x/35.x и т.д.) исчезают.

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

Дополнительно:
- SKIP-нутый сервис **не выпадает** из объединённого `dist/all/` — туда подмешивается его
  предыдущий опубликованный список (`meta.json` помечает такие сервисы в `stale_services`).
- Все файлы пишутся **атомарно** (tmp + rename) — nginx и bird-reloader никогда не увидят
  частично записанный файл.
- При нуле префиксов `wireguard.txt`/`nftables.conf` рендерятся comment-only предупреждением
  (пустое `AllowedIPs = ` заблокировало бы клиенту весь трафик).
- В `exabgp.conf` сосед/peer-as — плейсхолдеры (`203.0.113.1`/`64512`): поправьте под свой
  стенд (через CLI они пока не настраиваются; основной путь — BIRD-контейнер).

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

### Живой BGP-фид (BIRD) — профили `bgp` / `bgp-demo`

Контейнер `bird` (BIRD 2.x на Alpine) берёт собранные сети и анонсирует их подписчикам по BGP
с community-тегом, обновляя маршруты на лету (`birdc configure` при изменении файла).

```bash
cp .env.example .env            # выставьте FEED_ENABLED=1, FEED_ASN, FEED_COMMUNITY и т.д.

docker compose --profile bgp up -d --build        # collector + web + bird (продакшн-фид)
docker compose --profile bgp-demo up -d --build   # + демо-подписчик (peer) для проверки
```

Проверка демо-сессии:

```bash
docker compose exec bird birdc show protocols          # сессии Established
docker compose exec peer birdc show route all          # peer получил префиксы + community
```

- Маршруты — **`blackhole` + `next hop self`** (надёжный анонс списка префиксов из контейнера,
  без проблем достижимости next-hop). Генерирует их `collector` при `FEED_ENABLED=1` в `./feed`.
- **Подписчики**: явные сессии — в [`docker/bird/peers.conf`](docker/bird/peers.conf); быстрый
  одиночный пир — через `PEER_IP`/`PEER_ASN` в `.env`. Демо-пир и фид сидят на сети `bgpnet`
  со статическими адресами `172.31.0.10/20`.
- Подробности доставки — в [`bgp/README.md`](bgp/README.md).

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
