# Plan: Syslog and SNMP servers on the air-gapped LAN

> **Status: PROPOSED.** This is a deployment plan, not code. Decisions marked **DECIDE** need team
> agreement and an ADR (`docs/adr/`) before implementation; then update `PROJECT.md` in the same PR.
>
> Scope: the `collector` part of `PROJECT.md` §3 (roadmap phase 1, "Data in"), plus the
> "configure switches" path from the hackathon slide (pre-change preview, technician approval,
> one-click rollback).
>
> Device configs below are **templates**. Example server IP `10.10.10.50`, example names
> `moni-*`. Check every command against the exact IOS / IOS-XE / Junos version in the lab before
> rolling it out.

---

## 1. Goals

| # | Goal | Done when |
|---|---|---|
| G1 | Receive syslog from every Cisco and Juniper device (L0–L3) | Messages from all devices land in the DB, parsed, with the correct device, time and severity |
| G2 | Receive SNMP traps and informs | Link up/down, config change, environment and auth-failure events show up within 5 s |
| G3 | Poll SNMP (v3) for metrics, inventory and topology | Interface counters, CPU, memory, environment, LLDP/CDP, ARP and MAC tables stored per device |
| G4 | Configure switches from the server | Technician sees a diff and an impact preview, approves, the change applies, and can be rolled back in one click |
| G5 | Fully air-gapped | Nothing reaches the internet at build-on-site, startup or runtime; all MIBs, images and packages ship in the bundle |

---

## 2. Architecture

```
          Management network (OOB / mgmt VRF)                    Monicomm host (Docker)
 ┌────────────────────────────────────────┐   ┌──────────────────────────────────────────────────────┐
 │ Cisco IOS / IOS-XE / NX-OS             │   │  syslog      (Vector)     UDP/TCP 514, TLS 6514   ──┐  │
 │ Juniper EX / QFX / MX / SRX            │──►│  trapd       (net-snmp snmptrapd) UDP 162         ──┤  │
 │                                        │   │                                                     ▼  │
 │                                        │◄──│  snmp-poller (Telegraf snmp input) UDP 161 out   Redis │
 │                                        │   │                                                streams │
 │                                        │◄──│  configurator (Python: SNMP SET + NETCONF/SSH)     │   │
 │                                        │   │      ▲ human approval only, never called by AI     ▼   │
 │                                        │   │      │                              worker ─► Postgres │
 │ NTP ◄── all devices + Monicomm host    │   │   api / web (approval UI, diff, rollback)  +Timescale  │
 └────────────────────────────────────────┘   └──────────────────────────────────────────────────────┘
```

### 2.1 Services (new entries in `docker-compose.yml`)

| Service | Tech (**DECIDE**) | Listens / talks | Why this choice |
|---|---|---|---|
| `syslog` | **Vector** (single binary, disk buffers, parses RFC 3164 and 5424) | in: UDP 514, TCP 514, TLS 6514 | One container receives, parses, archives raw lines and pushes to Redis. Fallback: rsyslog + omhiredis if Vector misparses a vendor format. |
| `trapd` | **net-snmp `snmptrapd`** | in: UDP 162 | Reference implementation, handles v2c and v3 traps and informs, and loads Cisco/Juniper MIBs for decoding. Output goes to a file or stdout that Vector reads, so traps and syslog share one pipeline. |
| `snmp-poller` | **Telegraf** (`inputs.snmp`, gosnmp) | out: UDP 161 | Mature SNMPv3 polling, table walks, MIB translation, and a native Postgres/Timescale output. |
| `configurator` | **Python** (pysnmp, ncclient, scrapli) | out: UDP 161 (SET), TCP 830 (NETCONF), TCP 22 (SSH/SCP) | The only service allowed to write to devices. Separate container, separate credentials, separate audit log. Built in phase F. |
| `ntp` (optional) | chrony | UDP 123 | Only if the closed network has no NTP server. Syslog correlation is useless without synced clocks. |

### 2.2 Docker networking: the part that usually breaks

Syslog and traps identify the device **by source IP**. Docker can hide that:

- The userland proxy and some NAT paths rewrite the source IP to the Docker gateway, so every message looks like it came from `172.17.0.1`.
- UDP conntrack: after a container restart, stale conntrack entries can silently black-hole port 514/162 until they expire.

**Plan:** run `syslog` and `trapd` with `network_mode: host` (or a macvlan with its own IP on the mgmt LAN).
They reach Redis via a port published only on `127.0.0.1`. The rest of the stack stays on an internal
bridge network. Bind 514 with `cap_add: [NET_BIND_SERVICE]` and a non-root user.

> This conflicts with the `PROJECT.md` §5 test ("run the stack on an `internal: true` network").
> Collectors **must** reach the device LAN. Update §5: "app services on internal networks;
> collectors on host/macvlan, reaching only the mgmt subnets (host firewall)".

Sketch only (not final):

```yaml
syslog:
  image: timberio/vector:<exact-tag>@sha256:<digest>
  network_mode: host
  cap_add: [NET_BIND_SERVICE]
  volumes:
    - ./collector/vector:/etc/vector:ro
    - syslog-archive:/var/lib/monicomm/syslog     # raw lines, gzip per day per device
    - vector-buffer:/var/lib/vector               # disk buffer if Redis is down
trapd:
  build: ./collector/trapd                        # debian + net-snmp + MIBs, pinned
  network_mode: host
  volumes:
    - trapd-state:/var/lib/net-snmp               # keeps the engine ID stable across restarts
    - mibs:/usr/share/snmp/mibs:ro
snmp-poller:
  image: telegraf:<exact-tag>@sha256:<digest>
  networks: [mgmt, internal]
  volumes:
    - ./collector/telegraf:/etc/telegraf:ro
    - mibs:/usr/share/snmp/mibs:ro
```

### 2.3 Host firewall (Monicomm server)

| Port | Proto | Direction | From / to |
|---|---|---|---|
| 514 | UDP + TCP | in | mgmt subnets only |
| 6514 | TCP (TLS) | in | mgmt subnets only (if TLS syslog is used) |
| 162 | UDP | in | mgmt subnets only |
| 161 | UDP | out | devices |
| 830, 22 | TCP | out | devices (configurator only) |
| 123 | UDP | out/in | NTP |

### 2.4 Secrets

- SNMP users, auth/priv passwords and SSH/NETCONF credentials are **never** in git or `.env`.
  `.env.example` holds placeholders. Real values come from Docker secrets files on the host, created by `install.sh` from approved media.
- Separate credentials for **read** (poller, trapd) and **write** (configurator). The read set must not be able to change anything.
- Never in logs and never sent to the LLM (`PROJECT.md` §10).

---

## 3. Syslog design

### 3.1 Formats to handle

| Source | Typical format | Notes |
|---|---|---|
| Cisco IOS / IOS-XE | RFC 3164-like: `<189>123: host: *Nov 25 10:58:12.345 IST: %LINK-3-UPDOWN: Interface Gi1/0/1, changed state to down` | Sequence number, optional `*` (clock not synced), vendor timestamp inside the message. Parse `%FACILITY-SEVERITY-MNEMONIC`. |
| Cisco NX-OS | `2026 Nov 25 10:58:12.345 IST: %ETHPORT-5-IF_DOWN_LINK_FAILURE: ...` | Same mnemonic idea, different header. |
| Junos (default) | RFC 3164: `<28>Nov 25 10:58:12 sw1 mib2d[1234]: SNMP_TRAP_LINK_DOWN: ifIndex 512, ...` | Event tag in capitals. |
| Junos `structured-data` | RFC 5424 with SD-ID `[junos@2636...]` | **Preferred.** Clean key/value fields, year and ms in the timestamp. |

### 3.2 Pipeline

1. Vector receives → stamps `received_at` and `source_ip` → writes the raw line to the archive (evidence, `PROJECT.md` AI rule 4).
2. Vector parses the header (RFC 3164 or 5424) and pushes JSON to the Redis stream `ingest:syslog`.
3. The worker maps `source_ip` to `device_id` (inventory), extracts the vendor event code, normalizes it, and inserts into a Timescale hypertable `syslog_events`.
4. If Redis is down, Vector's disk buffer holds the data. Nothing is dropped silently, and a counter for dropped/buffered messages goes to the dashboard.

### 3.3 Normalized event types (starter list)

| Event | Cisco | Juniper |
|---|---|---|
| `link_down` / `link_up` | `%LINK-3-UPDOWN`, `%LINEPROTO-5-UPDOWN` | `SNMP_TRAP_LINK_DOWN` / `_UP` |
| `config_change` | `%SYS-5-CONFIG_I`, `%PARSER-5-CFGLOG_LOGGEDCMD` | `UI_COMMIT`, `UI_COMMIT_COMPLETED`, `UI_CMDLINE_READ_LINE` |
| `login_failed` | `%SEC_LOGIN-4-LOGIN_FAILED` | `SSHD_LOGIN_FAILED`, `LOGIN_FAILED` |
| `bgp_state` | `%BGP-5-ADJCHANGE` | `RPD_BGP_NEIGHBOR_STATE_CHANGED` |
| `ospf_state` | `%OSPF-5-ADJCHG` | `RPD_OSPF_NBRDOWN` / `NBRUP` |
| `stp_change` | `%SPANTREE-*` | `L2ALD_*` / `ESWD_*` STP messages (check per platform) |
| `hw_env` | `%ENVMON-*`, `%PLATFORM-*` | `CHASSISD_*` |

Unknown codes are kept as `other` with the raw code. The Analyzer's log clustering groups them later.

### 3.4 Retention (**DECIDE**, `PROJECT.md` open question 7)

- Parsed events: hot 30 days, Timescale compression after 7 days.
- Raw archive: gzip files, 1 year (or whatever the unit's policy requires).

---

## 4. SNMP design

### 4.1 Version and crypto (common denominator for Cisco and Juniper)

- **SNMPv3, `authPriv`, SHA (SHA-1) + AES-128.** Every IOS, IOS-XE, NX-OS and Junos version in use supports this.
  Use SHA-2 (SHA-256 and up) only where every device supports it. Check this in the lab.
- v2c only for legacy devices that can't do v3, read-only, behind an ACL, listed as an exception.

### 4.2 Polling (Telegraf)

| Data | MIB / OID | Interval | Used by |
|---|---|---|---|
| Identity | SNMPv2-MIB `sysName`, `sysDescr`, `sysObjectID`, `sysUpTime` | 5 min | Mapper, inventory (vendor/model from sysObjectID) |
| Interfaces | IF-MIB `ifXTable` (HC 64-bit counters), `ifOperStatus`, `ifAdminStatus`, errors, discards | 60 s | Dashboard, Analyzer |
| Inventory | ENTITY-MIB (`entPhysicalTable`: serials, modules, PSUs) | 1 h | Mapper / documentation tool |
| Neighbors | LLDP-MIB (both vendors), CISCO-CDP-MIB (Cisco) | 5 min | Mapper topology |
| ARP | IP-MIB `ipNetToPhysicalTable` (fallback `ipNetToMediaTable`) | 5 min | Mapper (IP ↔ MAC) |
| MAC table | BRIDGE-MIB / Q-BRIDGE-MIB `dot1qTpFdbTable` | 5 min | Mapper (MAC ↔ port) |
| CPU / memory | Cisco: CISCO-PROCESS-MIB `cpmCPUTotal5minRev`, CISCO-MEMORY-POOL / ENHANCED-MEMPOOL · Juniper: JUNIPER-MIB `jnxOperatingCPU`, `jnxOperatingBuffer` | 60 s | Dashboard, anomalies |
| Environment | Cisco: CISCO-ENVMON-MIB · Juniper: `jnxOperatingTemp`, `jnxOperatingState` | 5 min | Dashboard |

**Cisco MAC-table gotcha:** on Catalyst switches the MAC table is per VLAN. With v3 you query the
context `vlan-<id>`, so the SNMP group needs `context vlan- match prefix` (template below).
Without it the MAC table comes back empty.

**Interface index:** set `snmp-server ifindex persist` on Cisco so `ifIndex` survives reloads. Junos
keeps `ifIndex` stable by default.

### 4.3 Traps vs informs

| | Traps | Informs (**recommended**) |
|---|---|---|
| Delivery | Fire and forget, lost if the server is down | Acknowledged and retried |
| v3 engine ID | Receiver must know **each device's** engine ID (one `createUser -e` per device) | Device must know the **receiver's** engine ID (one value in the template for all devices) |

Plan: **informs** everywhere they're supported, traps as a fallback.
`trapd` must keep a **fixed engine ID**, so `/var/lib/net-snmp` lives on a named volume and the value
is recorded in the device templates. A changed engine ID breaks informs from every device.

Traps to enable (both vendors): linkUp/linkDown, coldStart/warmStart, authenticationFailure, config
change, entity/FRU, environment (PSU, fan, temperature), BGP/OSPF state, CPU threshold.

### 4.4 MIBs (offline)

- Download on the build machine: Cisco MIB bundle (the MIBs for the exact platforms) and the Juniper MIB
  package for each Junos release in use.
- Put them in the bundle as a `mibs` volume, with a checksum. Telegraf (gosmi) and snmptrapd both load them.
- Nothing fetches MIBs at runtime.

---

## 5. Device templates (onboarding)

Apply with the existing change process, one device first, then a pilot group, then everything.
Each template sets: NTP, timestamps, source interface, syslog host, SNMPv3 read user, inform target.

### 5.1 Cisco IOS / IOS-XE

```
! --- time and log format ---
ntp server 10.10.10.1
clock timezone IST 2 0
service timestamps log datetime msec localtime show-timezone year
service sequence-numbers
!
! --- syslog ---
logging origin-id hostname
logging source-interface Loopback0              ! or the mgmt interface; add "vrf Mgmt-vrf" if logging via mgmt VRF
logging host 10.10.10.50 transport udp port 514 ! tcp is also supported; TLS on newer IOS-XE
logging trap informational
logging buffered 64000 informational
!
! --- log every config command (feeds "what changed" / impact analyzer) ---
archive
 log config
  logging enable
  notify syslog contenttype plaintext
  hidekeys
 path flash:archive/cfg-
 maximum 14
!
! --- SNMPv3 read-only ---
ip access-list standard MONI-SNMP
 permit 10.10.10.50
snmp-server view MONI-RO iso included
snmp-server group MONI-RO-GRP v3 priv read MONI-RO access MONI-SNMP
snmp-server group MONI-RO-GRP v3 priv context vlan- match prefix read MONI-RO access MONI-SNMP
snmp-server user moni-poll MONI-RO-GRP v3 auth sha <AUTH> priv aes 128 <PRIV> access MONI-SNMP
snmp-server ifindex persist
snmp-server trap-source Loopback0
!
! --- informs (needs the receiver's engine ID) ---
snmp-server engineID remote 10.10.10.50 <TRAPD_ENGINE_ID_HEX>
snmp-server user moni-trap MONI-RO-GRP remote 10.10.10.50 v3 auth sha <AUTH> priv aes 128 <PRIV>
snmp-server host 10.10.10.50 informs version 3 priv moni-trap
snmp-server enable traps snmp linkdown linkup coldstart warmstart authentication
snmp-server enable traps config
snmp-server enable traps entity
snmp-server enable traps envmon
snmp-server enable traps bgp
snmp-server enable traps ospf state-change
snmp-server enable traps cpu threshold
```

`archive path` is also what makes `configure terminal revert timer` and `configure replace` work (phase F rollback).
NX-OS and ASA use different syntax. Add their templates once we know which models are in the network.

### 5.2 Juniper Junos (EX / QFX / MX / SRX)

```
# --- time and log format ---
set system ntp server 10.10.10.1
set system time-zone Asia/Jerusalem
set system syslog time-format year millisecond
#
# --- syslog (RFC 5424 structured data) ---
set system syslog host 10.10.10.50 any info
set system syslog host 10.10.10.50 authorization info
set system syslog host 10.10.10.50 interactive-commands info
set system syslog host 10.10.10.50 change-log info
set system syslog host 10.10.10.50 structured-data
set system syslog host 10.10.10.50 source-address 10.0.0.1
# if management-instance is enabled:
# set system syslog host 10.10.10.50 routing-instance mgmt_junos
#
# --- SNMPv3 read-only ---
set snmp engine-id use-mac-address
set snmp view MONI-ALL oid .1 include
set snmp v3 usm local-engine user moni-poll authentication-sha authentication-password "<AUTH>"
set snmp v3 usm local-engine user moni-poll privacy-aes128 privacy-password "<PRIV>"
set snmp v3 vacm security-to-group security-model usm security-name moni-poll group MONI-RO
set snmp v3 vacm access group MONI-RO default-context-prefix security-model usm security-level privacy read-view MONI-ALL
#
# --- informs to Monicomm ---
set snmp v3 usm remote-engine <TRAPD_ENGINE_ID_HEX> user moni-trap authentication-sha authentication-password "<AUTH>"
set snmp v3 usm remote-engine <TRAPD_ENGINE_ID_HEX> user moni-trap privacy-aes128 privacy-password "<PRIV>"
set snmp v3 target-address MONI address 10.10.10.50
set snmp v3 target-address MONI port 162
set snmp v3 target-address MONI tag-list moni-tag
set snmp v3 target-address MONI target-parameters MONI-TP
set snmp v3 target-parameters MONI-TP parameters message-processing-model v3 security-model usm security-level privacy security-name moni-trap
set snmp v3 target-parameters MONI-TP notify-filter MONI-NF
set snmp v3 notify MONI-N type inform tag moni-tag
set snmp v3 notify-filter MONI-NF oid .1 include
set snmp trap-options source-address 10.0.0.1
```

Restrict SNMP access with a firewall filter on `lo0` (or the mgmt interface) that only allows the Monicomm IP on UDP 161.

### 5.3 Onboarding checklist per device

- [ ] Clock synced (`show ntp status` / `show ntp associations`)
- [ ] Test syslog arrives (`send log 7 "moni test"` on Cisco; `logger -e TEST "moni test"` from the Junos shell)
- [ ] `snmpwalk -v3 -l authPriv ... sysName` from the poller container works
- [ ] A test inform arrives (shut/no shut a spare port, or Cisco `test snmp trap ...` / Junos `request snmp spoof-trap linkDown ...`)
- [ ] The device appears in inventory with the right vendor, model and interfaces

---

## 6. Configuring switches from the server (phase F)

### 6.1 What SNMP can and can't do

SNMP SET is a narrow tool for configuration. Plan for it honestly:

| Operation | Cisco via SNMP SET | Juniper via SNMP SET |
|---|---|---|
| Port shut / no shut | ✅ IF-MIB `ifAdminStatus` | ❌ not writable on Junos → NETCONF |
| Port description | ✅ IF-MIB `ifAlias` | ❌ → NETCONF |
| Access VLAN on a port | ✅ CISCO-VLAN-MEMBERSHIP-MIB `vmVlan` | ❌ → NETCONF |
| Back up running config | ✅ CISCO-CONFIG-COPY-MIB → SCP/SFTP server | ❌ → NETCONF `get-config` |
| Push config | ⚠️ CONFIG-COPY to running (merges, doesn't replace; risky) | ❌ |
| Commit with auto-rollback | ❌ | ❌ |

Junos allows SET only on a few utility MIBs (ping, traceroute, jnxUtil, SNMP config tables). Check your Junos version, but don't plan on SNMP to configure Juniper.

**Recommendation (DECIDE):** the "SNMP server" UI configures devices through a `configurator` service that uses:

- **SNMP SET** for the quick Cisco port operations above (shut/no shut, description, access VLAN), and
- **NETCONF** (TCP 830) for everything else and for **all** Juniper changes. NETCONF gives real
  diffs, validation and safe rollback on both vendors: Junos natively; IOS-XE with `netconf-yang`
  plus the candidate datastore. SSH/CLI (scrapli) is the fallback for old IOS without NETCONF.

### 6.2 Change flow (matches the slide: preview → approve → apply → one-click rollback)

1. **Snapshot:** fetch and store the running config (versioned in the DB).
2. **Preview:** show the exact diff (or the exact OIDs and values for a SET) plus the impact analyzer
   output (affected ports, VLANs, neighbors, and traffic on those links from SNMP counters).
3. **Approve:** a technician with the `admin` (or new `operator`) role clicks Approve. Optional second approver for core devices.
4. **Apply with a safety net:**
   - Junos: `commit confirmed 5` over NETCONF.
   - IOS-XE NETCONF: confirmed commit on the candidate datastore.
   - Classic IOS CLI: `configure terminal revert timer 5`, then `configure confirm`.
   - Cisco SNMP SET: store the previous value and write it back on rollback.
5. **Verify:** for 2–5 minutes, watch SNMP/syslog for the affected device (link states, errors, neighbor loss).
   If healthy → confirm. If not, or nobody confirms → the device rolls back by itself.
6. **Rollback button** at any later time: Junos `rollback N`; Cisco `configure replace flash:archive/cfg-N`; SNMP restores the stored previous value.
7. **Audit:** who, what, when, diff, result, and the rollback point. All of it.

### 6.3 Rules this must respect

- `CLAUDE.md` rule 3 and `PROJECT.md` §3 AI rule 3: **AI tools stay read-only.** The chat assistant
  ("ChatIAF") can explain a change, predict impact and draft it, but it can't apply it. Only a human
  click in the approval UI calls `configurator`, and the LLM has no tool that reaches it.
- Write credentials (Cisco `MONI-RW` group, NETCONF user) live only in `configurator`.
- This needs its own ADR, a security review and sign-off from the network owners before any write credential is created on a production device.

Cisco write user, restricted to only the OIDs we SET:

```
ip access-list standard MONI-SNMP-RW
 permit 10.10.10.50
snmp-server view MONI-RW 1.3.6.1.2.1.2.2.1.7 included        ! ifAdminStatus
snmp-server view MONI-RW 1.3.6.1.2.1.31.1.1.1.18 included    ! ifAlias
snmp-server view MONI-RW 1.3.6.1.4.1.9.9.68.1.2.2.1.2 included ! vmVlan
snmp-server view MONI-RW 1.3.6.1.4.1.9.9.96 included         ! CISCO-CONFIG-COPY-MIB
snmp-server group MONI-RW-GRP v3 priv read MONI-RO write MONI-RW access MONI-SNMP-RW
snmp-server user moni-cfg MONI-RW-GRP v3 auth sha <AUTH> priv aes 128 <PRIV> access MONI-SNMP-RW
snmp-server file-transfer access-group MONI-SNMP-RW protocol scp
```

---

## 7. Lab and testing (no real network needed)

| Need | Tool (all offline, in the bundle) |
|---|---|
| Fake SNMP devices | **snmpsim**: record `snmpwalk`s from real Cisco/Juniper devices once (`.snmprec`) and replay them as many agents. Great for dev and CI. |
| Real OS behavior | **containerlab** (or GNS3/EVE-NG) with vJunos-switch / vSRX and Cisco IOL / Cat8000v. Needs licensed images brought in on approved media. |
| Syslog load | `logger` / `loggen` replaying captured Cisco and Junos lines at the target EPS |
| Trap tests | `snmptrap` / `snmpinform` from net-snmp, plus real shut/no shut in the lab |
| Air-gap check | Run the stack with the host's outbound internet route removed; collectors still receive and poll |

Test cases to write: each sample line in §3.3 parses to the right event; a 3164 line without a year gets the
right year; a clock-unsynced Cisco line (`*` prefix) is flagged; 2× target EPS for 10 minutes with zero drops;
Redis down for 5 minutes recovers with no loss; trapd restart keeps the engine ID; v3 wrong password is rejected and logged.

---

## 8. Air-gapped delivery additions (`deploy/offline/`)

Add to the bundle (pinned by tag **and** digest, with checksums):

- Images: Vector, Telegraf, the `trapd` image (Debian + net-snmp), the `configurator` image, snmpsim (dev only), chrony (if needed).
- The MIB bundle (Cisco + Juniper, per platform and version).
- Python wheels for `configurator` (pysnmp, ncclient, scrapli), so there's no `pip install` on site.
- Device templates (§5) as text files, so the network team applies the same thing everywhere.

---

## 9. Rollout phases

| Phase | Work | Done when |
|---|---|---|
| **A. Decide + lab** | ADR for Vector / snmptrapd / Telegraf / configurator; get device models and OS versions; build the containerlab/snmpsim lab | ADR merged; lab has ≥1 Cisco and ≥1 Juniper reachable |
| **B. Syslog** | `syslog` service, raw archive, Redis stream, parser + normalization, Timescale table | Lab devices' logs are in the DB, parsed; load test passes |
| **C. Traps** | `trapd` with fixed engine ID, MIB decoding, into the same pipeline | Informs from both vendors arrive and decode to names, not raw OIDs |
| **D. Polling** | Telegraf configs per vendor (§4.2), Timescale output, inventory sync | Interface graphs, CPU/mem, LLDP/CDP and MAC/ARP data for lab devices |
| **E. Onboarding** | Templates applied to a pilot group of real devices, then all | Every device passes the §5.3 checklist |
| **F. Configure** | `configurator`, approval UI, preview/impact, confirmed commit, rollback, audit | Lab: change → approve → apply → auto-rollback on failure → manual rollback all work on both vendors |

A–E are read-only and safe. F touches device config and goes last, behind its own review.

---

## 10. Open questions (add to `PROJECT.md` §11)

1. Device list: which Cisco families (IOS, IOS-XE, NX-OS, ASA) and Juniper families (EX, QFX, MX, SRX), and which OS versions?
2. Is there an out-of-band management network or mgmt VRF? Which subnets?
3. Is there an NTP server inside the closed network?
4. Can every device do SNMPv3 with SHA + AES-128? Any v2c-only legacy devices?
5. Expected syslog volume (messages per second, peak) and number of devices.
6. Is TLS syslog (6514) required by the unit's security policy, or is UDP/TCP on the mgmt network acceptable?
7. Are write actions on devices approved at all? By whom? Which devices are excluded (core, crypto)?
8. Is NETCONF allowed (enable `netconf-yang` on IOS-XE, `set system services netconf ssh` on Junos)?
9. Retention for parsed events and raw syslog archive.
