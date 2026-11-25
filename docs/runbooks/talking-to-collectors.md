# How to talk to the syslog server and the SNMP server

Who talks to the two collector servers, how, and the commands to check each path. Setup is in
`collector-servers-setup.md`; design is in `../plans/syslog-snmp-deployment.md`.

## Quick reference

| | Syslog server `moni-syslog` | SNMP server `moni-snmp` |
|---|---|---|
| IP | `192.168.108.141` | `192.168.108.142` |
| Devices send to it | syslog: **UDP 514** (default), TCP 514, TLS 6514 (if enabled) | traps/informs: **UDP 162**, SNMPv3 user `moni-trap` |
| It sends to devices | nothing | SNMPv3 GET/WALK on **UDP 161**, user `moni-poll` (read-only) |
| It sends to Monicomm | TCP 6000 to `192.168.108.140` (mTLS) | TCP 6000 to `192.168.108.140` (mTLS) |
| Folder on the VM | `/opt/monicomm/collector/syslog-server` | `/opt/monicomm/collector/snmp-server` |
| Data on the VM | `/srv/monicomm/syslog-archive/<date>/<device-ip>.log.gz` | `/srv/monicomm/trapd-out/traps-<date>.jsonl` |

Data only flows **one way**: devices → collectors → Monicomm. The collectors have no query API. Nobody
"asks" them for data; they push everything to Monicomm. To ask a **device** something, use `snmpq` on the
SNMP server (section 4).

All `docker compose` commands below run as root in the server's folder (`sudo -i`, then `cd /opt/monicomm/collector/<server>`).

---

## 1. Devices → syslog server

**What it accepts**

| Transport | Port | Framing | Notes |
|---|---|---|---|
| UDP | 514 | one message per packet | Default for Cisco and Junos. Use this unless policy says otherwise. |
| TCP | 514 | one message per line (newline) | Cisco `transport tcp`. Messages using octet-counting framing on 514 are not supported. |
| TLS | 6514 | octet-counting (RFC 5425) | Commented out in `syslog-server/vector/vector.yaml` until the policy decision. |

Formats: RFC 3164 (Cisco, Junos default) and RFC 5424 (Junos `structured-data`, preferred). Unparseable
headers are still stored and forwarded with `parse_error`; nothing is dropped.

**The one rule:** the device is identified by the **source IP** of the packet, not by the hostname inside the
message. Always set a stable source interface (Cisco `logging source-interface Loopback0`, Junos
`source-address`). Also make sure the source IP is in the `ufw` allow rules on `moni-syslog`.

**Minimal device config** (full templates: plan §5):

```
! Cisco IOS / IOS-XE
service timestamps log datetime msec localtime show-timezone year
logging source-interface Loopback0
logging host 192.168.108.141 transport udp port 514
logging trap informational
```

```
# Junos
set system syslog host 192.168.108.141 any info
set system syslog host 192.168.108.141 structured-data
set system syslog host 192.168.108.141 source-address <device-mgmt-ip>
set system syslog time-format year millisecond
```

**Send a test message**

From any Linux host on the LAN:

```bash
logger -n 192.168.108.141 -P 514 -d "moni test from $(hostname)"          # UDP
logger -n 192.168.108.141 -P 514 -T "moni test over TCP from $(hostname)"  # TCP
```

From a Windows machine on the LAN (PowerShell):

```powershell
$u = New-Object System.Net.Sockets.UdpClient; $b = [Text.Encoding]::ASCII.GetBytes("<189>moni-test: %SYS-5-CONFIG_I: test from $env:COMPUTERNAME"); [void]$u.Send($b, $b.Length, "192.168.108.141", 514); $u.Close()
```

From a Cisco device: `send log 7 "moni test"`. From Junos (shell): `logger -e TEST "moni test"`.

---

## 2. Devices → SNMP server (traps and informs)

**What devices need** (must match `secrets/snmp_trap.env` on `moni-snmp`):

| Setting | Value |
|---|---|
| Target | `192.168.108.142`, UDP 162 |
| Type | **inform** (acknowledged, recommended) or trap |
| SNMP version / level | v3, authPriv |
| User | `TRAP_USER` (default `moni-trap`) |
| Auth / priv | `TRAP_AUTH_PROTOCOL` / `TRAP_PRIV_PROTOCOL` (default SHA / AES-128) and their passwords |
| Remote engine ID (informs) | `TRAPD_ENGINE_ID` without `0x` (default `80001f88046d6f6e692d7472617064`) |

Device config: plan §5.1 (Cisco `snmp-server engineID remote` + `snmp-server host ... informs version 3 priv moni-trap`)
and §5.3 (Junos `usm remote-engine` + `notify ... type inform`).

- **Informs** work for every device with the one engine ID above.
- **Plain v3 traps** need each device's own engine ID in `TRAP_DEVICE_ENGINE_IDS` (Cisco `show snmp engineID`,
  Junos `show snmp v3`), then `docker compose restart trapd`.
- **v2c** (legacy only): set `TRAP_V2C_COMMUNITY`, then restart trapd.

**Send a test inform**

On `moni-snmp` (uses the trap credentials from `secrets/`, nothing typed):

```bash
./snmpq test-inform           # "inform acknowledged by trapd"
```

From another Linux host with net-snmp tools (`snmp` package):

```bash
snmpinform -v3 -l authPriv -u moni-trap -a SHA -A '<trap-auth>' -x AES -X '<trap-priv>' \
  -e 0x80001f88046d6f6e692d7472617064 192.168.108.142:162 '' .1.3.6.1.6.3.1.1.5.3
```

No answer means a wrong engine ID, user, password or protocol, or a firewall.

---

## 3. SNMP server → devices (polling)

The poller reads `inventory/devices.csv`:

```
name,ip,vendor,role
core-sw-01,192.168.108.10,cisco,switch
edge-rtr-01,192.168.108.1,cisco,router
fw-srx-01,192.168.108.2,juniper,firewall
```

- `vendor`: `cisco` or `juniper`. `role`: `switch`, `router` or `firewall`.
- Every device: system, interfaces (60 s), LLDP, ARP, identity (5 min), hardware inventory (1 h).
- Cisco: CPU/memory (60 s), temperature/fan/PSU and CDP (5 min). Juniper: component state/CPU/memory/temperature (60 s).
- Routers and firewalls: BGP peers and OSPF neighbors (60 s).

After editing: `docker compose restart poller`, then `docker compose logs poller | head` shows
`poller: 10-all.conf: N device(s)` per template.

**What devices need:** an SNMPv3 user that matches `secrets/snmp_ro.env` (default `moni-poll`, SHA/AES-128,
read-only view), and an ACL that allows `192.168.108.142` on UDP 161 (plan §5).

---

## 4. Operators → SNMP server

**`snmpq`**: ad-hoc read-only SNMP using the stored credentials (no passwords on the command line).
Run it in `/opt/monicomm/collector/snmp-server`:

```bash
./snmpq get 192.168.108.10 .1.3.6.1.2.1.1.5.0 .1.3.6.1.2.1.1.3.0   # sysName, sysUpTime
./snmpq walk 192.168.108.10                                       # system group
./snmpq bulkwalk 192.168.108.10 .1.3.6.1.2.1.31.1.1.1.1           # interface names
./snmpq test-inform                                               # trap path check
./snmpq poll-test                                                 # run every Telegraf poll once, print results
```

There is no `set`. Device changes go through the configurator (plan §7), never ad hoc.

Useful OIDs (output is numeric because no MIB files are loaded):

| What | OID |
|---|---|
| sysDescr / sysName / sysUpTime | `.1.3.6.1.2.1.1.1.0` / `.1.3.6.1.2.1.1.5.0` / `.1.3.6.1.2.1.1.3.0` |
| Interface names | `.1.3.6.1.2.1.31.1.1.1.1` |
| Interface oper status (1 up, 2 down) | `.1.3.6.1.2.1.2.2.1.8` |
| Interface descriptions | `.1.3.6.1.2.1.31.1.1.1.18` |
| LLDP neighbor names | `.1.0.8802.1.1.2.1.4.1.1.9` |
| ARP table (IP → MAC) | `.1.3.6.1.2.1.4.22.1.2` |
| BGP peer states (6 = established) | `.1.3.6.1.2.1.15.3.1.2` |
| Cisco CPU 5 min | `.1.3.6.1.4.1.9.9.109.1.1.1.1.8` |
| Juniper component CPU | `.1.3.6.1.4.1.2636.3.1.13.1.8` |

**Watch traps arrive**

```bash
tail -f /srv/monicomm/trapd-out/traps-$(date -u +%F).jsonl
docker compose logs -f trapd        # also logs each trap and any v3 auth failures
```

**Watch what the SNMP server sends to Monicomm**

```bash
docker compose exec shipper vector tap --url http://127.0.0.1:8687/graphql traps_norm metrics_norm
docker compose exec shipper vector top --url http://127.0.0.1:8687/graphql     # live counters, q to quit
```

---

## 5. Operators → syslog server

```bash
docker compose ps                                  # running?
docker compose logs --tail 50                      # errors (TLS to Monicomm, bind failures)
docker compose exec vector vector tap normalize    # live: every message as it will be sent to Monicomm
docker compose exec vector vector top              # live counters per component, q to quit
```

Raw archive (one gzip file per device per day, UTC date). The current file is still open, so `zcat` may warn
"unexpected end of file". That's harmless:

```bash
ls /srv/monicomm/syslog-archive/$(date -u +%F)/
zcat /srv/monicomm/syslog-archive/$(date -u +%F)/192.168.108.10.log.gz 2>/dev/null | tail
zgrep -h "LINK-3-UPDOWN" /srv/monicomm/syslog-archive/*/192.168.108.10.log.gz 2>/dev/null | tail
```

Each archive line is `<received-at UTC> <source IP> <message as received>`.

Is Monicomm keeping up? If `to_monicomm` in `vector top` shows events in but not out, Monicomm is unreachable
and the disk buffer is filling (`du -sh /srv/monicomm/vector-buffer`). Nothing is lost until the buffer is full.

---

## 6. Monicomm (developers) ← both servers

- The collectors **push** to Monicomm `ingest` on TCP 6000 (Vector protocol, mutual TLS). Monicomm never
  connects to the collectors for data, and never to devices.
- The event format is defined in `collector/README.md` (`monicomm.syslog.v1`, `monicomm.trap.v1`,
  `monicomm.snmp_metric.v1`, plus collector health metrics).
- **Until Monicomm exists**, `dev-ingest` on `192.168.108.140` writes everything to
  `/opt/monicomm/collector/dev-ingest/data/<UTC date>/{syslog,trap,snmp_metric,collector_health}.jsonl`,
  one JSON object per line. Build and test parsers against these files.

```bash
tail -f /opt/monicomm/collector/dev-ingest/data/$(date -u +%F)/syslog.jsonl
```

```python
import json, datetime
day = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
with open(f"/opt/monicomm/collector/dev-ingest/data/{day}/syslog.jsonl") as f:
    for line in f:
        ev = json.loads(line)
        sev = ev.get("syslog", {}).get("severity", "?")
        print(ev["received_at"], ev["source_ip"], sev, ev["raw"])
```

- **Later (PROPOSED):** Monicomm's own `ingest` service (Vector) receives the same stream and writes it to Redis
  streams (`ingest:syslog`, `ingest:trap`, `ingest:snmp_metric`) for the workers. The event format stays the same.

---

## 7. Don'ts

- Don't give the poller user write access on devices, and don't add `set` to `snmpq`. Writes are phase F, behind approval.
- Don't type SNMP passwords on command lines (shell history). Use `snmpq` or the secret files.
- Don't point devices at Monicomm (`.140`) or let Monicomm poll devices. Only the collectors talk to devices.
- Don't change `TRAPD_ENGINE_ID` after devices are configured. Every device's informs would break.
