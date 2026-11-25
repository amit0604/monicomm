#!/usr/bin/env bash
# Builds the air-gapped bundle for the syslog server and SNMP server VMs.
# Run on the CONNECTED build machine (Linux + Docker). Output:
#   deploy/offline/dist/monicomm-collectors-<date>.tar  and  .tar.sha256
# Carry both into the closed network on approved media, then follow
# docs/runbooks/collector-servers-setup.md.
set -euo pipefail

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
DIST="$ROOT/deploy/offline/dist"
NAME="monicomm-collectors-$(date -u +%Y%m%d)"
STAGE="$DIST/$NAME"

# Ubuntu 24.04 image used only to download Docker Engine .deb files for the VMs.
UBUNTU_IMAGE="ubuntu:noble-20261024.1@sha256:fe81560990fae86dc4743202b2cb4d3df98d0bcf949173cecef15ce1127ef852"
# Docker Engine packages for the VMs (Ubuntu 24.04 "noble"). Bump deliberately, never "latest".
DOCKER_CE_VERSION="${DOCKER_CE_VERSION:-5:29.9.3-1~ubuntu.24.04~noble}"
CONTAINERD_VERSION="${CONTAINERD_VERSION:-2.4.2-4~ubuntu.24.04~noble}"
COMPOSE_VERSION="${COMPOSE_VERSION:-5.8.0-1~ubuntu.24.04~noble}"
BUILDX_VERSION="${BUILDX_VERSION:-0.39.1-1~ubuntu.24.04~noble}"

image_from() { awk -v pat="$2" '$1 == "image:" && $2 ~ pat {print $2; exit}' "$1"; }
VECTOR_IMAGE="$(image_from "$ROOT/collector/syslog-server/docker-compose.yml" '^timberio/vector')"
TELEGRAF_IMAGE="$(image_from "$ROOT/collector/snmp-server/docker-compose.yml" '^telegraf')"
TRAPD_IMAGE="$(image_from "$ROOT/collector/snmp-server/docker-compose.yml" '^monicomm/trapd')"

rm -rf "$STAGE"
mkdir -p "$STAGE"/{images,debs}

echo "== images"
docker pull "$VECTOR_IMAGE"
docker pull "$TELEGRAF_IMAGE"
docker build -t "$TRAPD_IMAGE" "$ROOT/collector/snmp-server/trapd"
docker save "$VECTOR_IMAGE" "$TELEGRAF_IMAGE" "$TRAPD_IMAGE" | gzip > "$STAGE/images/collector-images.tar.gz"
printf '%s\n' "$VECTOR_IMAGE" "$TELEGRAF_IMAGE" "$TRAPD_IMAGE" > "$STAGE/images/IMAGES"

echo "== Docker Engine .deb packages for Ubuntu 24.04"
docker run --rm -v "$STAGE/debs:/out" "$UBUNTU_IMAGE" bash -euc "
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  echo 'deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu noble stable' \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq --download-only \
    docker-ce=$DOCKER_CE_VERSION docker-ce-cli=$DOCKER_CE_VERSION containerd.io=$CONTAINERD_VERSION \
    docker-compose-plugin=$COMPOSE_VERSION docker-buildx-plugin=$BUILDX_VERSION >/dev/null
  cp /var/cache/apt/archives/*.deb /out/
"

echo "== collector files (no secrets, certs or site inventory)"
mkdir -p "$STAGE/collector" "$STAGE/docs"
tar -C "$ROOT/collector" \
  --exclude='secrets/*.env' --exclude='certs/*.crt' --exclude='certs/*.key' \
  --exclude='inventory/devices.csv' --exclude='pki/out' --exclude='dev-ingest/data' \
  -cf - . | tar -C "$STAGE/collector" -xf -
cp "$ROOT/deploy/offline/install-collector.sh" "$STAGE/"
cp "$ROOT/docs/runbooks/collector-servers-setup.md" "$ROOT/docs/plans/syslog-snmp-deployment.md" "$STAGE/docs/"

echo "== checksums"
(cd "$STAGE" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
tar -C "$DIST" -cf "$DIST/$NAME.tar" "$NAME"
(cd "$DIST" && sha256sum "$NAME.tar" > "$NAME.tar.sha256")
rm -rf "$STAGE"

echo "done: $DIST/$NAME.tar"
cat "$DIST/$NAME.tar.sha256"
