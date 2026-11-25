#!/usr/bin/env bash
# End-to-end test of the syslog server and SNMP server deployments on one Docker host.
# No real network devices: a test container runs net-snmp snmpd and sends syslog + an inform.
#
#   collector/test/e2e.sh
#
# Checks: syslog (UDP + TCP) reaches ingest and the raw archive; a v3 inform with the fixed
# engine ID reaches ingest; Telegraf polls the device over SNMPv3; events sent while ingest is
# down are buffered and delivered after it comes back.
set -euo pipefail
export MSYS_NO_PATHCONV=1   # Git Bash on Windows: don't rewrite container paths

HERE="$(cd "$(dirname "$0")/.." && pwd)"
P=moni-e2e
NET="$P-net"
VECTOR_IMAGE="$(awk '/image: timberio\/vector/ {print $2; exit}' "$HERE/syslog-server/docker-compose.yml")"
TELEGRAF_IMAGE="$(awk '/image: telegraf/ {print $2; exit}' "$HERE/snmp-server/docker-compose.yml")"
TRAPD_IMAGE="$P-trapd"
DEVICE_IMAGE="$P-device"
ENGINE_ID=0x80001f88046d6f6e692d7472617064

WORK="$(mktemp -d "${TMPDIR:-/tmp}/moni-e2e.XXXXXX")"
hostpath() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else echo "$1"; fi; }
W="$(hostpath "$WORK")"

cleanup() {
  docker rm -f "$P-ingest" "$P-syslog" "$P-snmp" "$P-trapd" "$P-poller" "$P-device" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  if [[ "${KEEP_WORK:-}" == 1 ]]; then echo "work dir kept: $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT

pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*"; docker logs --tail 40 "$P-ingest" 2>&1 | sed 's/^/  ingest| /'; exit 1; }

# wait_for <seconds> <file glob> <pattern>
wait_for() {
  local deadline=$((SECONDS + $1)) glob="$2" pattern="$3"
  while (( SECONDS < deadline )); do
    # shellcheck disable=SC2086
    if grep -qs -- "$pattern" $glob 2>/dev/null; then return 0; fi
    sleep 3
  done
  return 1
}

echo "== build images"
docker build -q -t "$TRAPD_IMAGE" "$(hostpath "$HERE/snmp-server/trapd")" >/dev/null
docker build -q -t "$DEVICE_IMAGE" - >/dev/null <<'EOF'
FROM debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2
RUN apt-get update && apt-get install -y --no-install-recommends snmpd snmp && rm -rf /var/lib/apt/lists/*
ENV MIBS=""
RUN printf '%s\n' \
  'agentAddress udp:161' \
  'createUser moni-poll SHA "e2e-poll-auth" AES "e2e-poll-priv"' \
  'rouser moni-poll priv' \
  'sysName e2e-device' > /etc/snmp/e2e.conf
CMD ["snmpd", "-f", "-Lo", "-C", "-c", "/etc/snmp/e2e.conf"]
EOF

echo "== certificates and config"
OUT_DIR="$WORK/pki" bash "$HERE/pki/make-certs.sh" ingest >/dev/null
mkdir -p "$WORK"/{ingest-data,archive,syslog-buffer,snmp-buffer,trapd-state,trapd-out,inventory,secrets}
cat > "$WORK/secrets/snmp_ro.env" <<'EOF'
SNMP_USER=moni-poll
SNMP_AUTH_PASS=e2e-poll-auth
SNMP_PRIV_PASS=e2e-poll-priv
EOF
cat > "$WORK/secrets/snmp_trap.env" <<EOF
TRAPD_ENGINE_ID=$ENGINE_ID
TRAP_USER=moni-trap
TRAP_AUTH_PASS=e2e-trap-auth
TRAP_PRIV_PASS=e2e-trap-priv
EOF

docker network create "$NET" >/dev/null

echo "== start dev-ingest (stand-in for Monicomm)"
docker run -d --name "$P-ingest" --network "$NET" --network-alias ingest \
  -v "$(hostpath "$HERE/dev-ingest/vector.yaml"):/etc/vector/vector.yaml:ro" \
  -v "$W/pki/ingest:/etc/monicomm/certs:ro" \
  -v "$W/ingest-data:/data" \
  "$VECTOR_IMAGE" --config /etc/vector/vector.yaml >/dev/null

echo "== start syslog server"
docker run -d --name "$P-syslog" --network "$NET" \
  -e VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true -e COLLECTOR_ID=e2e-syslog -e MONICOMM_INGEST_ADDRESS=ingest:6000 \
  -e FORWARD_BUFFER_BYTES=268435488 -e UDP_RECEIVE_BUFFER_BYTES=1048576 \
  -v "$(hostpath "$HERE/syslog-server/vector"):/etc/vector:ro" \
  -v "$W/pki/syslog-server:/etc/monicomm/certs:ro" \
  -v "$W/archive:/var/lib/monicomm/syslog" \
  -v "$W/syslog-buffer:/var/lib/vector" \
  "$VECTOR_IMAGE" --config /etc/vector/vector.yaml >/dev/null

echo "== start device"
docker run -d --name "$P-device" --network "$NET" "$DEVICE_IMAGE" >/dev/null
DEVICE_IP="$(docker inspect -f "{{(index .NetworkSettings.Networks \"$NET\").IPAddress}}" "$P-device")"
printf 'name,ip,vendor,role\ne2e-device,%s,cisco,router\n' "$DEVICE_IP" > "$WORK/inventory/devices.csv"

echo "== start SNMP server (shipper, trapd, poller share one network namespace, like host mode)"
docker run -d --name "$P-snmp" --network "$NET" \
  -e VECTOR_DANGEROUSLY_ALLOW_ENV_VAR_INTERPOLATION=true -e COLLECTOR_ID=e2e-snmp -e MONICOMM_INGEST_ADDRESS=ingest:6000 -e FORWARD_BUFFER_BYTES=268435488 \
  -v "$(hostpath "$HERE/snmp-server/vector"):/etc/vector:ro" \
  -v "$W/pki/snmp-server:/etc/monicomm/certs:ro" \
  -v "$W/trapd-out:/var/log/trapd:ro" \
  -v "$W/snmp-buffer:/var/lib/vector" \
  "$VECTOR_IMAGE" --config /etc/vector/vector.yaml >/dev/null
docker run -d --name "$P-trapd" --network "container:$P-snmp" \
  -v "$W/secrets/snmp_trap.env:/run/secrets/snmp_trap:ro" \
  -v "$W/trapd-state:/var/lib/net-snmp" \
  -v "$W/trapd-out:/var/log/trapd" \
  "$TRAPD_IMAGE" >/dev/null
docker run -d --name "$P-poller" --network "container:$P-snmp" \
  --entrypoint /bin/sh \
  -v "$(hostpath "$HERE/snmp-server/telegraf"):/etc/telegraf:ro" \
  -v "$W/inventory:/etc/monicomm/inventory:ro" \
  -v "$W/secrets/snmp_ro.env:/run/secrets/snmp_ro:ro" \
  "$TELEGRAF_IMAGE" /etc/telegraf/entrypoint.sh >/dev/null

sleep 8
for c in ingest syslog snmp trapd poller device; do
  [[ "$(docker inspect -f '{{.State.Running}}' "$P-$c")" == true ]] || { docker logs "$P-$c"; fail "container $c is not running"; }
done
pass "all containers running"

echo "== send syslog (UDP RFC 3164 Cisco-style, TCP RFC 5424 Junos-style) and a v3 inform"
docker exec "$P-device" logger -n "$P-syslog" -P 514 -d --rfc3164 -t e2e \
  "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/1, changed state to down"
docker exec "$P-device" logger -n "$P-syslog" -P 514 -T --rfc5424 -t mib2d \
  "SNMP_TRAP_LINK_DOWN: ifIndex 512, ifAdminStatus up(1), ifOperStatus down(2), ifName ge-0/0/1"
docker exec "$P-device" snmpinform -v3 -l authPriv -u moni-trap -a SHA -A e2e-trap-auth \
  -x AES -X e2e-trap-priv -e "$ENGINE_ID" "$P-snmp:162" '' \
  .1.3.6.1.6.3.1.1.5.3 .1.3.6.1.2.1.2.2.1.1.7 i 7 \
  || fail "inform not acknowledged (engine ID or v3 user mismatch)"
pass "inform acknowledged by trapd"

day="$(date -u +%F)"
wait_for 60 "$WORK/ingest-data/$day/syslog.jsonl" "LINK-3-UPDOWN" || fail "UDP syslog did not reach ingest"
pass "UDP syslog reached ingest"
wait_for 30 "$WORK/ingest-data/$day/syslog.jsonl" "SNMP_TRAP_LINK_DOWN" || fail "TCP syslog did not reach ingest"
pass "TCP syslog reached ingest"
grep -q '"source_ip":"'"$DEVICE_IP"'"' "$WORK/ingest-data/$day/syslog.jsonl" || fail "syslog source_ip is not the device IP"
pass "syslog source_ip is the device IP ($DEVICE_IP)"
wait_for 60 "$WORK/ingest-data/$day/trap.jsonl" '"trap_oid":".1.3.6.1.6.3.1.1.5.3"' || fail "inform did not reach ingest"
pass "inform reached ingest as linkDown"

sleep 65   # let the gzip archive file close (idle_timeout_secs: 60)
docker run --rm -v "$W/archive:/a:ro" debian:trixie-20261104-slim@sha256:a72b4433de1cf7d6bae0c4cee74d0547f58601a643b3375f070c51600d63b6b2 \
  sh -c "zcat /a/*/$DEVICE_IP.log.gz | grep -q LINK-3-UPDOWN" || fail "raw archive missing the syslog line"
pass "raw archive has the syslog line"

wait_for 120 "$WORK/ingest-data/$day/snmp_metric.jsonl" '"measurement":"snmp_interface"' || { docker logs --tail 30 "$P-poller"; fail "no SNMP interface metrics"; }
pass "SNMPv3 polling: interface metrics reached ingest"
grep -q '"sysName":"e2e-device"' "$WORK/ingest-data/$day/snmp_metric.jsonl" || fail "sysName tag missing"
pass "SNMPv3 polling: sysName tag present"
grep -q '"source_ip":"'"$DEVICE_IP"'"' "$WORK/ingest-data/$day/snmp_metric.jsonl" || fail "metric source_ip is not the device IP"
pass "SNMPv3 polling: source_ip is the device IP"

echo "== buffering: stop ingest, send, start ingest"
docker stop "$P-ingest" >/dev/null
docker exec "$P-device" logger -n "$P-syslog" -P 514 -d --rfc3164 -t e2e "BUFFER-TEST while ingest is down"
sleep 10
docker start "$P-ingest" >/dev/null
wait_for 120 "$WORK/ingest-data/$day/syslog.jsonl" "BUFFER-TEST" || fail "buffered event was not delivered after ingest came back"
pass "event sent while ingest was down was delivered after restart"

echo "ALL PASSED"
