# BGP-фид (доставка по образцу antifilter.download)

Этот каталог — про живую доставку собранных сетей по BGP. Сами списки генерирует
`bgpcollect collect` (см. корневой README), а здесь — как анонсировать их подписчикам.

## Идея

Демон BIRD/ExaBGP держит BGP-сессии с роутерами-подписчиками и анонсирует все собранные
префиксы, помечая их BGP-community (по умолчанию `65432:500`, как у antifilter). Подписчик
импортирует только маршруты с этим community и заворачивает их в нужный аплинк/туннель.

## Генерация конфигов

```bash
# из готового объединённого списка
bgpcollect feed -i dist/all/ipv4.txt -o /etc/bird/bgpcollect \
    --asn 65000 --next-hop 192.0.2.1 --community 65432:500
```

Создаёт:
- `bgpcollect_routes.conf` — статический протокол BIRD со всеми сетями + фильтр экспорта
  `bgpcollect_export`, помечающий маршруты community.
- `exabgp.conf` — эквивалент для ExaBGP.

## Подключение в BIRD 2.x

В основном `bird.conf`:

```
include "/etc/bird/bgpcollect/bgpcollect_routes.conf";

protocol bgp subscriber1 {
    local as 65000;
    neighbor 203.0.113.1 as 64512;
    ipv4 {
        import none;
        export filter bgpcollect_export;   # отдаёт только наши маршруты с community
    };
}
```

Применить обновления без рестарта сессий: `birdc configure`.

## Автообновление

`bgpcollect.service` (+ `bgpcollect.timer`) в этом каталоге: периодически пересобирает списки,
регенерирует конфиг и делает `birdc configure`. Скопируйте в `/etc/systemd/system/`,
поправьте `--asn/--next-hop/--neighbor` и включите таймер.

## Проверка конфига перед применением

```bash
bird -p -c /etc/bird/bird.conf     # синтаксическая проверка без запуска
```
