# Демо-подписчик: BIRD, который пирится к фиду и принимает маршруты (для проверки).
FROM alpine:3.22

RUN apk add --no-cache bird2 && mkdir -p /run/bird

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

ENV FEED_IP=172.31.0.10 \
    FEED_ASN=65000 \
    PEER_ASN=64512 \
    ROUTER_ID=172.31.0.20

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
