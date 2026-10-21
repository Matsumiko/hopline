FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/hopline/app

# sing-box is the tunnel engine; pin via build arg so upgrades are explicit.
ARG SING_BOX_VERSION=1.14.3
ARG TARGETARCH=amd64

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl tar \
 && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    arch="${TARGETARCH}"; \
    case "${arch}" in \
      amd64) sb_arch="amd64" ;; \
      arm64) sb_arch="arm64" ;; \
      *) echo "unsupported arch ${arch}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL -o /tmp/sing-box.tar.gz \
      "https://github.com/SagerNet/sing-box/releases/download/v${SING_BOX_VERSION}/sing-box-${SING_BOX_VERSION}-linux-${sb_arch}.tar.gz"; \
    tar -xzf /tmp/sing-box.tar.gz -C /tmp; \
    install -m 0755 "/tmp/sing-box-${SING_BOX_VERSION}-linux-${sb_arch}/sing-box" /usr/local/bin/sing-box; \
    rm -rf /tmp/sing-box*

WORKDIR /opt/hopline/app
COPY hopline/ /opt/hopline/app/hopline/

RUN groupadd --system hopline \
 && useradd --system --gid hopline --home-dir /var/lib/hopline --shell /usr/sbin/nologin hopline \
 && install -d -o hopline -g hopline -m 0700 /var/lib/hopline \
 && install -d -o root -g root -m 0755 /etc/hopline

USER hopline
WORKDIR /var/lib/hopline

# Control, gateway, and metrics must stay localhost-only; see SECURITY.md.
EXPOSE 18770 18772 18773

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python3 -c "import socket,sys; s=socket.socket(); s.settimeout(3); sys.exit(0 if s.connect_ex(('127.0.0.1',18772))==0 else 1)"

ENTRYPOINT ["python3", "-m", "hopline"]
CMD ["run", "--config", "/etc/hopline/hopline.toml"]
