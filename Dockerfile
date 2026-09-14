FROM alpine:3.22

RUN apk add --no-cache \
    bash \
    curl \
    wget \
    git \
    libstdc++ \
    gcompat \
    libatomic

WORKDIR /opt

ARG OVS_VERSION

RUN test -n "$OVS_VERSION"

RUN wget -q \
    "https://github.com/gitpod-io/openvscode-server/releases/download/${OVS_VERSION}/${OVS_VERSION}-linux-x64.tar.gz" \
    -O openvscode.tar.gz \
    && tar -xzf openvscode.tar.gz \
    && mv ${OVS_VERSION}-linux-x64 openvscode \
    && rm openvscode.tar.gz

WORKDIR /workspace

EXPOSE 10000

CMD ["/opt/openvscode/bin/openvscode-server", \
     "--host", "0.0.0.0", \
     "--port", "10000", \
     "--without-connection-token"]
