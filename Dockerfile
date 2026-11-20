# syntax=docker/dockerfile:1.7
# Pinpoint ExApp image. Targets:
#   release  what AppAPI deploys (HaRP-ready: frpc + start.sh, as in nextcloud/app-skeleton-python)
#   dev      the same runtime with the source mounted, for docker compose in dev/

#############################
# Frontend build
#############################
FROM node:22-bookworm-slim AS frontend
WORKDIR /build
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund
COPY vite.config.ts tsconfig.json ./
COPY src ./src
RUN npm run build

#############################
# Python dependencies + FRP client
#############################
FROM python:3.12-slim-bookworm AS builder
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m pip install --root-user-action=ignore -r /requirements.txt

ARG FRP_VERSION=0.71.1
ARG FRP_AMD64_SHA256=1d9875210972a5d1a62b2dc4c48df45ab0af05d3ca1b5e494a014428259df803
ARG FRP_ARM64_SHA256=8edf590b0c396fa42f9c147121a76af83cfc2002b08f5aef0ea1008c43482019
RUN set -eux; \
    case "$(uname -m)" in aarch64) arch=arm64; sum="$FRP_ARM64_SHA256";; *) arch=amd64; sum="$FRP_AMD64_SHA256";; esac; \
    curl -fsSL "https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_${arch}.tar.gz" -o /tmp/frp.tgz; \
    echo "${sum}  /tmp/frp.tgz" | sha256sum -c -; \
    tar -C /tmp -xzf /tmp/frp.tgz; \
    install -m 0755 "/tmp/frp_${FRP_VERSION}_linux_${arch}/frpc" /usr/local/bin/frpc; \
    rm -rf /tmp/frp*

#############################
# Runtime
#############################
FROM python:3.12-slim-bookworm AS runtime
# Tesseract reads scans and photos; the language packs match the default "OCR languages" setting.
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-deu tesseract-ocr-fra tesseract-ocr-spa \
        tesseract-ocr-ita tesseract-ocr-nld tesseract-ocr-por tesseract-ocr-tur \
        curl procps \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/ /usr/local/
COPY --chmod=755 start.sh healthcheck.sh /
WORKDIR /ex_app/lib
HEALTHCHECK --interval=5s --timeout=3s --retries=120 CMD /healthcheck.sh

FROM runtime AS dev
# Source, js/ and img/ are mounted by dev/docker-compose.yml.
CMD ["python3", "main.py"]

FROM runtime AS release
COPY ex_app/img /ex_app/img
COPY ex_app/lib /ex_app/lib
COPY --from=frontend /build/ex_app/js /ex_app/js
ENTRYPOINT ["/start.sh", "python3", "main.py"]
