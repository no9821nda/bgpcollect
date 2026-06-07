# Образ BGP-фида на BIRD 2.x (Alpine).
FROM alpine:3.22

RUN apk add --no-cache bird2 \
    && mkdir -p /run/bird /etc/bird /etc/bird/feed

COPY bird.conf   /etc/bird/bird.conf
COPY peers.conf  /etc/bird/peers.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 179/tcp

ENV FEED_ASN=65000 \
    ROUTER_ID=10.255.255.1 \
    FEED_COMMUNITY=65432:500 \
    BIRD_RELOAD_INTERVAL=30

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
