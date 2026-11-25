# EVE-NG POC lab: simulated Cisco and Juniper devices

A small lab for testing the syslog server and SNMP server without real network gear or vendor images.
It runs on an EVE-NG Community host and builds **Linux nodes that behave like a Cisco and a Juniper switch**:

| Node | IP (default) | Looks like | Sends |
|---|---|---|---|
| `lab-cisco1` | `10.100.102.161` | Cisco Catalyst 2960-X, IOS 15.2 | `%LINK-3-UPDOWN`, `%SYS-5-CONFIG_I`, `%SEC_LOGIN-4-LOGIN_FAILED` |
| `lab-junos1` | `10.100.102.162` | Juniper EX2300, Junos 21.4 | `SNMP_TRAP_LINK_DOWN/UP`, `UI_COMMIT`, `SSHD_LOGIN_FAILED` |

Each node runs:
- **net-snmp `snmpd`:** an SNMPv3 agent (`moni-poll`, authPriv) with a vendor `sysDescr`/`sysObjectID` marked
  `[Monicomm lab simulation]`. It sends **linkDown/linkUp informs** (`moni-trap`) when a port changes, checked every 5 s.
- **rsyslog:** forwards everything to the syslog server (UDP 514).
- **Four dummy "ports"** (`port1`..`port4`) that really go down and up.
- **`moni-sim`:** makes events on demand. A timer also makes a random event every ~15 min.

The nodes are joined to the LAN through EVE-NG's **Cloud0** (`pnet0`), so the collectors see them like any device.

**Lab only.** Vendor-specific MIBs (CPU, environment, CDP, BGP) aren't there, since these are Linux nodes.
Swap in real IOL/vIOS/vJunos images from your vendor account when you need them.

## Build

On the EVE-NG host, as root, with internet access (it downloads the Ubuntu 24.04 cloud image and checks it
against Ubuntu's SHA256SUMS):

```bash
# 1. The SNMP credentials the nodes must use: copy these lines from the SNMP server's
#    collector/snmp-server/secrets/snmp_ro.env and snmp_trap.env (never commit them)
install -m 600 /dev/null /root/moni-lab/moni-snmp.env
nano /root/moni-lab/moni-snmp.env     # SNMP_USER, SNMP_AUTH_PASS, SNMP_PRIV_PASS, TRAP_USER, TRAP_AUTH_PASS, TRAP_PRIV_PASS

# 2. Build images, write the lab, start the nodes (defaults match the home lab; override as needed)
COLLECTOR=10.100.102.254 GATEWAY=10.100.102.1 DNS=10.100.102.53 \
SSH_PUBKEY="$(cat ~/.ssh/id_ed25519.pub)" ./build-lab.sh
```

To change node names, IPs or MACs, edit `NODES` at the top of `build-lab.sh`. Every node needs its own MAC.
The lab then shows up in the EVE-NG web UI as `monicomm-poc`. The nodes' root password is in
`/root/moni-lab/node-root-password` on the EVE-NG host.

Then add the nodes to the SNMP server's `inventory/devices.csv` (`vendor` = `cisco` / `juniper`) and run
`docker compose restart poller`.

## Use

On a node, as root (EVE-NG console, or SSH with the key you passed as `SSH_PUBKEY`):

```bash
moni-sim flap port2     # link down 5 s, then up: linkDown + linkUp informs and vendor-style syslog
moni-sim down port3     # and: moni-sim up port3
moni-sim config         # config-change syslog
moni-sim login-fail     # failed-login syslog
```

Check from the SNMP server: `./snmpq get 10.100.102.161 .1.3.6.1.2.1.1.1.0` (sysDescr).

## Notes

- Requirements: about 0.5 GB RAM per node, plus EVE-NG's own ~1.5 GB.
- When `snmpd` starts, it sends linkUp informs for interfaces that are already up. Expect that noise after a boot.
- If you change files in `node/`, re-run `build-lab.sh`. It rebuilds the images. In EVE-NG, wipe the nodes
  (stop, Wipe) before starting them on new images.
