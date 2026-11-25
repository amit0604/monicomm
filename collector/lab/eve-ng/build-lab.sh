#!/usr/bin/env bash
# Builds the Monicomm POC lab on an EVE-NG Community host: two Linux nodes that act like a Cisco
# and a Juniper switch (net-snmp SNMPv3 agent, rsyslog, vendor-style messages) on Cloud0 (the LAN),
# sending syslog and SNMPv3 informs to the Monicomm collectors. See README.md.
#
# Run as root on the EVE-NG host, from this folder:
#   SECRETS=/root/moni-lab/moni-snmp.env ./build-lab.sh
#
# Lab/dev tool only. It downloads the Ubuntu cloud image from cloud-images.ubuntu.com, so it needs
# internet on the EVE-NG host; it is not part of the air-gapped delivery.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
WORK="${WORK:-/root/moni-lab}"
SECRETS="${SECRETS:-$WORK/moni-snmp.env}"   # SNMP_USER/.._PASS and TRAP_USER/.._PASS from the SNMP server's secrets
COLLECTOR="${COLLECTOR:-10.100.102.254}"     # host running the syslog + SNMP servers
GATEWAY="${GATEWAY:-10.100.102.1}"
DNS="${DNS:-10.100.102.53}"
PREFIX="${PREFIX:-24}"
SSH_PUBKEY="${SSH_PUBKEY:-}"                 # optional: public key allowed to SSH in as root
LAB="${LAB:-/opt/unetlab/labs/monicomm-poc.unl}"
Q=/opt/unetlab/addons/qemu
W=/opt/unetlab/wrappers/unl_wrapper
IMG_BASE=https://cloud-images.ubuntu.com/releases/noble/release
IMG=ubuntu-24.04-server-cloudimg-amd64.img

# name  ip  style  mac (each node needs its own MAC on the LAN)
NODES=(
  "lab-cisco1 10.100.102.161 cisco 52:54:00:4d:01:61"
  "lab-junos1 10.100.102.162 junos 52:54:00:4d:01:62"
)

die() { echo "error: $*" >&2; exit 1; }
[[ $EUID -eq 0 ]] || die "run as root on the EVE-NG host"
[[ -x $W ]] || die "EVE-NG not found ($W)"
[[ -r $SECRETS ]] || die "missing $SECRETS (copy the SNMP_*/TRAP_* lines from the SNMP server's secrets/*.env)"
command -v virt-customize >/dev/null || die "virt-customize missing (apt install guestfs-tools)"
mkdir -p "$WORK"

echo "== Ubuntu cloud image (verified against Ubuntu's SHA256SUMS)"
curl -fsSL -o "$WORK/SHA256SUMS" "$IMG_BASE/SHA256SUMS"
[[ -f $WORK/$IMG ]] || curl -fsSL -o "$WORK/$IMG" "$IMG_BASE/$IMG"
want=$(grep " \*$IMG\$" "$WORK/SHA256SUMS" | cut -d' ' -f1)
got=$(sha256sum "$WORK/$IMG" | cut -d' ' -f1)
[[ -n $want && $want == "$got" ]] || die "checksum mismatch for $IMG"

echo "== base image (snmpd, rsyslog, moni-sim, boot setup)"
[[ -f $WORK/node-root-password ]] || (umask 077; tr -dc A-Za-z0-9 </dev/urandom | head -c 20 >"$WORK/node-root-password")
grep -E '^(SNMP_USER|SNMP_AUTH_PASS|SNMP_PRIV_PASS|TRAP_USER|TRAP_AUTH_PASS|TRAP_PRIV_PASS)=' "$SECRETS" >"$WORK/moni-snmp.node.env"
chmod 600 "$WORK/moni-snmp.node.env"
mkdir -p "$Q/linux-moni-base"
qemu-img convert -O qcow2 "$WORK/$IMG" "$Q/linux-moni-base/virtioa.qcow2"
args=(
  --install snmpd,snmp,rsyslog
  --run-command 'touch /etc/cloud/cloud-init.disabled'
  --upload "$HERE/node/moni-node-setup:/usr/local/sbin/moni-node-setup" --chmod 0755:/usr/local/sbin/moni-node-setup
  --upload "$HERE/node/moni-sim:/usr/local/bin/moni-sim" --chmod 0755:/usr/local/bin/moni-sim
  --upload "$HERE/node/moni-node-setup.service:/etc/systemd/system/moni-node-setup.service"
  --upload "$HERE/node/moni-chatter.service:/etc/systemd/system/moni-chatter.service"
  --upload "$HERE/node/moni-chatter.timer:/etc/systemd/system/moni-chatter.timer"
  --mkdir /etc/systemd/system/snmpd.service.d
  --upload "$HERE/node/snmpd-override.conf:/etc/systemd/system/snmpd.service.d/override.conf"
  --upload "$WORK/moni-snmp.node.env:/etc/moni-snmp.env" --chmod 0600:/etc/moni-snmp.env
  --run-command 'systemctl enable moni-node-setup.service moni-chatter.timer'
  --root-password "file:$WORK/node-root-password"
  --timezone UTC
)
[[ -n $SSH_PUBKEY ]] && args+=(--ssh-inject "root:string:$SSH_PUBKEY")
virt-customize -a "$Q/linux-moni-base/virtioa.qcow2" "${args[@]}"

echo "== per-node images"
for spec in "${NODES[@]}"; do
  read -r name ip style _mac <<<"$spec"
  d="$Q/linux-moni-${name#lab-}"
  rm -rf "$d" && mkdir -p "$d"
  qemu-img create -q -f qcow2 -F qcow2 -b "$Q/linux-moni-base/virtioa.qcow2" "$d/virtioa.qcow2"
  printf 'NODE_NAME=%s\nNODE_IP=%s/%s\nGATEWAY=%s\nDNS=%s\nSTYLE=%s\nCOLLECTOR=%s\n' \
    "$name" "$ip" "$PREFIX" "$GATEWAY" "$DNS" "$style" "$COLLECTOR" >"$WORK/$name.conf"
  virt-customize -q -a "$d/virtioa.qcow2" --no-network --upload "$WORK/$name.conf:/etc/moni-node.conf"
  echo "  $name  $ip  ($style)"
done

echo "== lab file $LAB"
uuid() { cat /proc/sys/kernel/random/uuid; }
qopts="-machine type=pc,accel=kvm -vga std -usbdevice tablet -boot order=cd -cpu host"
{
  echo '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
  echo "<lab name=\"monicomm-poc\" id=\"$(uuid)\" version=\"1\" scripttimeout=\"300\" lock=\"0\" author=\"monicomm\">"
  echo "  <description>Monicomm POC: simulated Cisco and Juniper nodes (Linux + net-snmp) on Cloud0, sending syslog/SNMPv3 to $COLLECTOR</description>"
  echo '  <topology>'
  echo '    <nodes>'
  i=0
  for spec in "${NODES[@]}"; do
    read -r name _ip _style mac <<<"$spec"
    i=$((i + 1))
    echo "      <node id=\"$i\" name=\"$name\" firstmac=\"$mac\" type=\"qemu\" template=\"linux\" image=\"linux-moni-${name#lab-}\" console=\"vnc\" cpu=\"1\" cpulimit=\"1\" ram=\"512\" ethernet=\"1\" uuid=\"$(uuid)\" qemu_options=\"$qopts\" qemu_version=\"2.12.0\" qemu_arch=\"x86_64\" qemu_nic=\"virtio-net-pci\" delay=\"0\" icon=\"Server-2D-Linux-S.svg\" config=\"0\" left=\"$((i * 300))\" top=\"300\">"
    echo '        <interface id="0" name="e0" type="ethernet" network_id="1"/>'
    echo '      </node>'
  done
  echo '    </nodes>'
  echo '    <networks>'
  echo '      <network id="1" type="pnet0" name="Cloud0 (LAN)" left="450" top="120" visibility="1"/>'
  echo '    </networks>'
  echo '  </topology>'
  echo '</lab>'
} >"$LAB"
$W -a fixpermissions >/dev/null 2>&1 || true

echo "== start nodes"
for id in $(seq 1 ${#NODES[@]}); do
  $W -a start -T 0 -F "$LAB" -D "$id" >/dev/null 2>&1 || true
done
echo "done. Nodes boot in ~30 s; check with: ping ${NODES[0]#* } (first node), then ./snmpq get <ip> .1.3.6.1.2.1.1.5.0 on the SNMP server"
