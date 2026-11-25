#!/bin/sh
# Generates Telegraf SNMP input configs from inventory/devices.csv and the templates,
# then starts Telegraf. Credentials come from the snmp_ro secret as environment variables
# that Telegraf substitutes (${SNMP_USER} etc.), so they never land in a config file.
set -eu

SECRET_FILE=/run/secrets/snmp_ro
INVENTORY=/etc/monicomm/inventory/devices.csv
TEMPLATES=/etc/telegraf/templates
OUT=/tmp/telegraf.d
V3_BLOCK=/tmp/snmp_v3_block

if [ ! -r "$SECRET_FILE" ]; then
  echo "poller: missing secret $SECRET_FILE" >&2
  exit 1
fi
if [ ! -r "$INVENTORY" ]; then
  echo "poller: missing $INVENTORY (copy inventory/devices.example.csv and edit)" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$SECRET_FILE"
set +a
: "${SNMP_USER:?set SNMP_USER in the snmp_ro secret}"
: "${SNMP_AUTH_PASS:?set SNMP_AUTH_PASS in the snmp_ro secret}"
: "${SNMP_PRIV_PASS:?set SNMP_PRIV_PASS in the snmp_ro secret}"
export SNMP_AUTH_PROTOCOL="${SNMP_AUTH_PROTOCOL:-SHA}"
export SNMP_PRIV_PROTOCOL="${SNMP_PRIV_PROTOCOL:-AES}"

cat > "$V3_BLOCK" <<'EOF'
  version = 3
  sec_level = "authPriv"
  sec_name = "${SNMP_USER}"
  auth_protocol = "${SNMP_AUTH_PROTOCOL}"
  auth_password = "${SNMP_AUTH_PASS}"
  priv_protocol = "${SNMP_PRIV_PROTOCOL}"
  priv_password = "${SNMP_PRIV_PASS}"
  timeout = "5s"
  retries = 2
  max_repetitions = 20
  agent_host_tag = "source"
EOF

mkdir -p "$OUT"
rm -f "$OUT"/*.conf

total=0
for tmpl in "$TEMPLATES"/*.conf.tmpl; do
  match=$(sed -n 's/^# moni-match:[[:space:]]*//p' "$tmpl" | head -n 1)
  vendor=$(printf '%s\n' "$match" | sed -n 's/.*vendor=\([^[:space:]]*\).*/\1/p')
  role=$(printf '%s\n' "$match" | sed -n 's/.*role=\([^[:space:]]*\).*/\1/p')
  vendor="${vendor:-*}"
  role="${role:-*}"

  # CSV columns: name,ip,vendor,role. "#" lines and the header are skipped.
  agents=$(awk -F, -v v="$vendor" -v r="$role" '
    NR == 1 || /^[[:space:]]*#/ || NF < 4 { next }
    {
      gsub(/[[:space:]\r]/, "")
      if ((v == "*" || index("|" v "|", "|" $3 "|")) && (r == "*" || index("|" r "|", "|" $4 "|"))) {
        printf "%s\"udp://%s:161\"", (n++ ? ", " : ""), $2
      }
    }' "$INVENTORY")

  name=$(basename "$tmpl" .tmpl)
  if [ -z "$agents" ]; then
    echo "poller: $name: no matching devices, skipped"
    continue
  fi
  count=$(printf '%s' "$agents" | tr ',' '\n' | grep -c udp)
  total=$((total + count))

  awk -v agents="[$agents]" -v block="$V3_BLOCK" '
    $1 == "@SNMP_V3@" { while ((getline line < block) > 0) print line; close(block); next }
    { gsub(/@AGENTS@/, agents); print }
  ' "$tmpl" > "$OUT/$name"
  echo "poller: $name: $count device(s)"
done

if [ "$total" -eq 0 ]; then
  echo "poller: no devices in $INVENTORY" >&2
  exit 1
fi

exec telegraf --config /etc/telegraf/telegraf.conf --config-directory "$OUT"
