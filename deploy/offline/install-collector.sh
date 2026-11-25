#!/usr/bin/env bash
# Installs a Monicomm collector from the offline bundle on an Ubuntu 24.04 VM (no internet).
# Run as root from the unpacked bundle folder:
#
#   sudo ./install-collector.sh docker                    # once per VM: Docker Engine from bundled .debs
#   sudo ./install-collector.sh syslog-server             # on the syslog server VM
#   sudo ./install-collector.sh snmp-server               # on the SNMP server VM
#   sudo ./install-collector.sh dev-ingest                # temporary Monicomm stand-in (optional)
#
# It never overwrites an existing .env, secrets, certs or inventory, so it is safe to re-run for upgrades.
set -euo pipefail

ROLE="${1:-}"
BUNDLE="$(cd "$(dirname "$0")" && pwd)"
TARGET=/opt/monicomm/collector
DATA=/srv/monicomm

die() { echo "error: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run as root (sudo)"
[[ -n "$ROLE" ]] || die "usage: $0 docker|syslog-server|snmp-server|dev-ingest"

verify_bundle() {
  if [[ -f "$BUNDLE/SHA256SUMS" ]]; then
    (cd "$BUNDLE" && sha256sum --quiet -c SHA256SUMS) || die "bundle checksum mismatch"
    echo "bundle checksums OK"
  fi
}

install_docker() {
  verify_bundle
  apt-get install -y --no-download "$BUNDLE"/debs/*.deb
  systemctl enable --now docker
  docker version --format 'docker {{.Server.Version}}'
  docker compose version
}

load_images() {
  docker load -i "$BUNDLE/images/collector-images.tar.gz"
  while read -r ref; do
    [[ -z "$ref" ]] && continue
    docker image inspect "$ref" >/dev/null 2>&1 \
      || die "image $ref not found after load (see runbook: troubleshooting, image digests)"
  done < "$BUNDLE/images/IMAGES"
  echo "images loaded and resolvable by tag@digest"
}

copy_files() {
  mkdir -p "$TARGET"
  # Copy code/config, keep site-specific files that already exist.
  tar -C "$BUNDLE/collector" \
    --exclude='.env' --exclude='*.env' --exclude='*.crt' --exclude='*.key' --exclude='devices.csv' \
    -cf - . | tar -C "$TARGET" -xf -
  chmod 700 "$TARGET/certs" "$TARGET"/snmp-server/secrets
  find "$TARGET" \( -name '*.sh' -o -name snmpq \) -exec chmod 755 {} +
}

ensure_env() {
  local dir="$TARGET/$1"
  if [[ ! -f "$dir/.env" ]]; then
    cp "$dir/.env.example" "$dir/.env"
    echo "created $dir/.env from .env.example: EDIT IT before starting"
  fi
}

host_tuning() {
  # Bigger UDP receive buffers for syslog/trap bursts (host networking uses the host's limits).
  cat > /etc/sysctl.d/90-monicomm-collector.conf <<'EOF'
net.core.rmem_max = 33554432
net.core.rmem_default = 8388608
net.core.netdev_max_backlog = 10000
EOF
  sysctl --system >/dev/null
}

retention_cron() {
  cat > /etc/cron.daily/monicomm-collector-retention <<'EOF'
#!/bin/sh
# Monicomm collector retention (docs/plans/syslog-snmp-deployment.md §3.4). Edit the day counts per unit policy.
find /srv/monicomm/syslog-archive -mindepth 1 -maxdepth 1 -type d -mtime +365 -exec rm -rf {} + 2>/dev/null
find /srv/monicomm/trapd-out -name 'traps-*.jsonl' -mtime +14 -delete 2>/dev/null
exit 0
EOF
  chmod 755 /etc/cron.daily/monicomm-collector-retention
}

case "$ROLE" in
  docker)
    install_docker
    ;;
  syslog-server)
    verify_bundle; load_images; copy_files; ensure_env syslog-server; host_tuning; retention_cron
    mkdir -p "$DATA/syslog-archive" "$DATA/vector-buffer"
    echo
    echo "next: edit $TARGET/syslog-server/.env, put certs in $TARGET/certs, then:"
    echo "  cd $TARGET/syslog-server && docker compose up -d"
    ;;
  snmp-server)
    verify_bundle; load_images; copy_files; ensure_env snmp-server; host_tuning; retention_cron
    mkdir -p "$DATA/trapd-state" "$DATA/trapd-out" "$DATA/vector-buffer"
    for s in snmp_ro snmp_trap; do
      f="$TARGET/snmp-server/secrets/$s.env"
      [[ -f "$f" ]] || { cp "$f.example" "$f"; chmod 600 "$f"; echo "created $f: EDIT IT (real passwords)"; }
    done
    inv="$TARGET/snmp-server/inventory/devices.csv"
    [[ -f "$inv" ]] || { cp "$TARGET/snmp-server/inventory/devices.example.csv" "$inv"; echo "created $inv: EDIT IT (your devices)"; }
    echo
    echo "next: edit .env, secrets/*.env and inventory/devices.csv in $TARGET/snmp-server, put certs in $TARGET/certs, then:"
    echo "  cd $TARGET/snmp-server && docker compose up -d"
    ;;
  dev-ingest)
    verify_bundle; load_images; copy_files
    echo
    echo "next: put ingest certs in $TARGET/certs, then:"
    echo "  cd $TARGET/dev-ingest && docker compose up -d"
    ;;
  *)
    die "unknown role: $ROLE"
    ;;
esac
