#!/usr/bin/env bash
# Creates a small internal CA and the mTLS certificates for collectors -> Monicomm ingest.
# Run once on an admin machine (or the Monicomm VM). Output: collector/pki/out/ (git-ignored).
#
#   ./make-certs.sh <ingest-ip> [syslog-server-ip] [snmp-server-ip]
#   (a DNS name works instead of an IP; the collectors' MONICOMM_INGEST_ADDRESS must use the same form)
#   OUT_DIR=/some/dir overrides the output folder.
#
# Then copy to each VM's /opt/monicomm/collector/certs/:
#   out/syslog-server/*  -> syslog server VM     (ca.crt, collector.crt, collector.key)
#   out/snmp-server/*    -> SNMP server VM       (ca.crt, collector.crt, collector.key)
#   out/ingest/*         -> Monicomm VM / dev-ingest (ca.crt, ingest.crt, ingest.key)
# Keep out/ca/ca.key offline (approved media); it is only needed to issue new certificates.
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <ingest-ip> [syslog-server-ip] [snmp-server-ip]" >&2
  exit 1
fi
INGEST_IP="$1"
SYSLOG_IP="${2:-}"
SNMP_IP="${3:-}"
DAYS_CA=3650
DAYS_LEAF=825
OUT="${OUT_DIR:-$(cd "$(dirname "$0")" && pwd)/out}"

mkdir -p "$OUT"/{ca,ingest,syslog-server,snmp-server}
umask 077

if [[ ! -f "$OUT/ca/ca.key" ]]; then
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$OUT/ca/ca.key"
  openssl req -x509 -new -key "$OUT/ca/ca.key" -sha256 -days "$DAYS_CA" \
    -subj "/O=Monicomm/CN=Monicomm Collector CA" \
    -addext "basicConstraints=critical,CA:TRUE" \
    -addext "keyUsage=critical,keyCertSign,cRLSign" \
    -out "$OUT/ca/ca.crt"
  echo "created CA"
fi

issue() {
  local dir="$1" name="$2" cn="$3" eku="$4" san="$5"
  openssl genpkey -algorithm EC -pkeyopt ec_paramgen_curve:P-256 -out "$OUT/$dir/$name.key"
  openssl req -new -key "$OUT/$dir/$name.key" -subj "/O=Monicomm/CN=$cn" -out "$OUT/$dir/$name.csr"
  local ext
  ext="$(mktemp)"
  {
    echo "basicConstraints=critical,CA:FALSE"
    echo "keyUsage=critical,digitalSignature"
    echo "extendedKeyUsage=$eku"
    [[ -n "$san" ]] && echo "subjectAltName=$san"
  } > "$ext"
  openssl x509 -req -in "$OUT/$dir/$name.csr" -CA "$OUT/ca/ca.crt" -CAkey "$OUT/ca/ca.key" \
    -CAcreateserial -days "$DAYS_LEAF" -sha256 -extfile "$ext" -out "$OUT/$dir/$name.crt"
  rm -f "$ext" "$OUT/$dir/$name.csr"
  cp "$OUT/ca/ca.crt" "$OUT/$dir/ca.crt"
  chmod 644 "$OUT/$dir/$name.crt" "$OUT/$dir/ca.crt"
  echo "issued $dir/$name.crt ($cn)"
}

# subjectAltName entry for an IP address or a DNS name.
san_for() {
  local addr="$1"
  [[ -z "$addr" ]] && return 0
  if [[ "$addr" =~ ^[0-9.]+$ || "$addr" == *:* ]]; then echo "IP:$addr"; else echo "DNS:$addr"; fi
}

issue ingest ingest "monicomm-ingest" "serverAuth" "$(san_for "$INGEST_IP")"
issue syslog-server collector "moni-syslog" "clientAuth" "$(san_for "$SYSLOG_IP")"
issue snmp-server collector "moni-snmp" "clientAuth" "$(san_for "$SNMP_IP")"

echo "done: $OUT"
