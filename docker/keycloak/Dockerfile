FROM quay.io/keycloak/keycloak:23.0 as builder

ENV KC_HEALTH_ENABLED=true
ENV KC_METRICS_ENABLED=true
ENV KC_FEATURES=token-exchange
ENV KC_DB=mysql

WORKDIR /opt/keycloak

RUN keytool -genkeypair -storepass password -storetype PKCS12 -keyalg RSA -keysize 2048 -dname "CN=server" -alias server -ext "SAN:c=DNS:localhost,IP:127.0.0.1" -keystore conf/server.keystore
RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:23.0

COPY --from=builder /opt/keycloak/ /opt/keycloak/

WORKDIR /opt/keycloak

# configuring email listener to send emails for specific events
ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start", "--optimized"]