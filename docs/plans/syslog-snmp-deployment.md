# Plan: Syslog and SNMP servers on the air-gapped LAN

> **Status: PROPOSED.** This is a deployment plan, not code. Decisions marked **DECIDE** need team
> agreement and an ADR (`docs/adr/`) before implementation.
>
> Scope: the collector side of roadmap phase 1 ("Data in") for **Cisco and Juniper switches, routers
> and firewalls**, plus the "configure devices" item from the hackathon slide (pre-change preview,
> technician approval, one-click rollback).
>
> Device configs below are **templates**. Example addresses: syslog server `192.168.108.141`,
> SNMP server `192.168.108.142`, NTP `<ntp-ip>`, Monicomm `192.168.108.140`. Check every command against
> the exact IOS / IOS-XE / IOS-XR / Junos version in the lab before rolling it out.

---

## 1. Goals

| # | Goal | Done when |
|---|---|---|
| G1 | Receive syslog from every Cisco and Juniper device (switches, routers, firewalls) | Messages from all devices land in Monicomm, parsed, with the correct device, time and severity |
| G2 | Receive SNMP traps and informs | Link, routing-peer, config-change, environment and auth-failure events show up within 5 s |
| G3 | Poll SNMP (v3) for metrics, inventory and topology | Interfaces, CPU, memory, environment, LLDP/CDP, ARP, MAC tables (switches) and routing peers (routers) stored per device |
| G4 | Configure devices from the SNMP server | Technician sees a diff and an impact preview, approves, the change applies, and can be rolled back in one click |
| G5 | **Syslog and SNMP servers are separate from the Monicomm deployment** | Each runs as its own Docker deployment on its own host, keeps working when Monicomm is down, and is the only thing that talks to network devices |
| G6 | Fully air-gapped | Nothing reaches the internet at install, startup or runtime; all MIBs, images and packages ship in the bundles |

---

## 2. Deployment model: three separate deployments

```
  Network devices (mgmt network / OOB / mgmt VRF)
  Cisco IOS, IOS-XE, IOS-XR, NX-OS · Juniper EX, QFX, MX, SRX
        │ syslog 514/6514                      ▲ SNMP 161, NETCONF 830, SSH 22
        │                    traps/informs 162 │            │
        ▼                                ▼     │            │
 ┌───────────────────────────┐   ┌─────────────┴────────────┴──────────────┐
 │ SYSLOG SERVER  (host A)   │   │ SNMP SERVER  (host B)                   │
 │ own docker compose        │   │ own docker compose                      │
 │                           │   │                                         │
 │  syslog-recv (Vector)     │   │  trapd (snmptrapd)   poller (Telegraf)  │
 │  raw archive (1 year)     │   │  configurator (writes, approval only)   │
 │  disk buffer              │   │  shipper (Vector) + disk buffer         │
 │  shipper (Vector)         │   │  device credentials live ONLY here      │
 └────────────┬──────────────┘   └──────────┬───────────────▲──────────────┘
              │ mTLS, TCP 6000              │ mTLS 6000      │ mTLS 8443 (configurator API,
              │ (events)                    │ (traps,metrics)│  target list)
              ▼                             ▼                │
 ┌────────────────────────────────────────────────────────────┴─────────────┐
 │ MONICOMM (host C) – existing docker compose, internal networks only      │
 │  ingest (Vector) ─► Redis ─► worker ─► Postgres/Timescale                │
 │  api / web (approval UI, diff, rollback) ─► calls configurator API       │
 │  blocked from devices (firewall), no device credentials                  │
 └──────────────────────────────────────────────────────────────────────────┘
```

### 2.1 Why separate

- **Collection survives Monicomm.** Upgrades, restarts or a broken Monicomm release don't lose
  syslog or traps. The collectors buffer to disk and catch up.
- **Smaller attack surface.** Only the syslog and SNMP servers talk to devices. Monicomm (web UI, LLM,
  user logins) is blocked from devices and holds no SNMP or NETCONF credentials. The current site uses one
  flat subnet (`192.168.108.0/24`), so the block is host firewall rules on the Monicomm VM (§2.5). A separate
  VLAN for Monicomm is stronger and can be added later without changing the deployments.
- **Security fit.** The AI lives on a host that physically cannot write to devices. Writes need the
  SNMP server's `configurator`, which only accepts approved requests (§10).
- **Independent life cycle.** The network team can own and patch the collectors. Other tools can
  read the raw syslog archive too.
- **Host networking is fine.** Each collector host is dedicated, so collectors can use host networking
  (keeps real device source IPs, avoids Docker UDP conntrack drops) without touching Monicomm's
  "internal networks only" rule (`PROJECT.md` §5).

Syslog and SNMP servers can be combined on one host for a small site (two compose projects, same
host). Keep them as two deployments either way, so they can be split later.

### 2.2 Services per deployment

| Deployment | Service | Tech (**DECIDE**) | Ports |
|---|---|---|---|
| Syslog server | `syslog-recv` + `shipper` | **Vector** (one container does both: receive, parse header, archive, forward) | in: UDP/TCP 514, TLS 6514, UDP 5514 (SRX traffic logs, §6.4) · out: TCP 6000 to Monicomm |
| SNMP server | `trapd` | **net-snmp `snmptrapd`** (traps + informs, MIB decoding) | in: UDP 162 |
| SNMP server | `poller` | **Telegraf** `inputs.snmp` | out: UDP 161 |
| SNMP server | `configurator` | **Python** (pysnmp, ncclient, scrapli) + small HTTPS API | out: UDP 161 (SET), TCP 830, TCP 22 · in: TCP 8443 from Monicomm only |
| SNMP server | `shipper` | **Vector** (reads trapd output and Telegraf metrics, forwards) | out: TCP 6000 to Monicomm |
| Monicomm | `ingest` (new, replaces `collector`) | **Vector** `vector` source | in: TCP 6000 from collector hosts only |
| either | `ntp` (optional) | chrony | Only if the closed network has no NTP server |

### 2.3 Interfaces between the deployments

| Link | Direction | Protocol | What |
|---|---|---|---|
| Events | collector → Monicomm | Vector-to-Vector over **mutual TLS**, TCP 6000 | Syslog events, traps, metrics as JSON, each with `collector_id`, `source_ip`, `received_at`, raw line |
| Target list | SNMP server ← Monicomm | HTTPS (mTLS) pull every 5 min, cached on disk | Devices to poll: IP, vendor, role, poll profile, **credential profile name** (never secrets). Polling continues from the cache if Monicomm is down. |
| Configure | Monicomm → SNMP server | HTTPS (mTLS), TCP 8443 | `snapshot`, `preview`, `apply`, `confirm`, `rollback`, `status`. Each request carries the approver and an approval ID (§10). |

- Certificates come from an internal CA (or one we generate at install). One client cert per collector and one for Monicomm.
- Monicomm is the **source of truth for the device inventory**. The SNMP server is the **source of
  truth for credentials**. Neither side holds the other's data.
- Active discovery (ICMP/ARP sweeps, optional nmap for the Mapper) also has to run from the SNMP
  server, because Monicomm is blocked from the devices. Expose it as another configurator-style
  API call (read-only). Design it in the Mapper's phase.

### 2.4 Compose sketch (each in its own folder, not final)

```yaml
# collector/syslog-server/docker-compose.yml
services:
  vector:
    image: timberio/vector:<exact-tag>@sha256:<digest>
    network_mode: host                 # real source IPs, no conntrack surprises
    cap_add: [NET_BIND_SERVICE]
    volumes:
      - ./vector:/etc/vector:ro
      - ./certs:/etc/vector/certs:ro
      - syslog-archive:/var/lib/monicomm/syslog   # raw lines, gzip per day per device
      - vector-buffer:/var/lib/vector             # disk buffer while Monicomm is unreachable

# collector/snmp-server/docker-compose.yml
services:
  trapd:
    build: ./trapd                     # debian + net-snmp + MIBs, pinned
    network_mode: host
    volumes: [trapd-state:/var/lib/net-snmp, mibs:/usr/share/snmp/mibs:ro, trap-out:/var/log/trapd]
  poller:
    image: telegraf:<exact-tag>@sha256:<digest>
    network_mode: host
    volumes: [./telegraf:/etc/telegraf:ro, mibs:/usr/share/snmp/mibs:ro, targets:/var/lib/targets:ro]
    secrets: [snmp_credentials]
  configurator:
    build: ./configurator
    network_mode: host
    secrets: [snmp_rw_credentials, netconf_credentials, api_tls]
  shipper:
    image: timberio/vector:<exact-tag>@sha256:<digest>
    network_mode: host
    volumes: [./vector:/etc/vector:ro, trap-out:/var/log/trapd:ro, vector-buffer:/var/lib/vector]
```

### 2.5 Host firewall

**Syslog server (A)**

| Port | Proto | Dir | Peer |
|---|---|---|---|
| 514 | UDP + TCP | in | mgmt subnets |
| 6514 | TCP (TLS) | in | mgmt subnets (if TLS syslog is used) |
| 5514 | UDP | in | SRX devices only (traffic logs, optional) |
| 6000 | TCP | out | Monicomm |
| 123 | UDP | out | NTP |

**SNMP server (B)**

| Port | Proto | Dir | Peer |
|---|---|---|---|
| 162 | UDP | in | mgmt subnets |
| 161 | UDP | out | devices |
| 830, 22 | TCP | out | devices (configurator only) |
| 8443 | TCP | in | Monicomm only |
| 6000 | TCP | out | Monicomm |
| 123 | UDP | out | NTP |

**Monicomm (C):** in 443 from users, in 6000 from A and B only, out 8443 to B only. Outbound SNMP (161),
SSH (22), Telnet (23) and NETCONF (830) toward device subnets explicitly denied, because on the flat
`192.168.108.0/24` LAN routing alone doesn't keep Monicomm away from devices (runbook step 5).

### 2.6 Secrets

- SNMP users, auth/priv passwords and SSH/NETCONF credentials exist **only on the SNMP server**, as
  Docker secrets files created at install from approved media. Never in git, `.env`, logs, Monicomm or the LLM.
- Separate **read** credentials (poller, trapd) and **write** credentials (configurator only).
- mTLS private keys: one per host, readable only by the service that uses it.

### 2.7 Hosting on VMware vSphere

The site has vSphere, so each deployment runs in its **own VM**. Starting sizes (adjust after the volume test):

| VM | IP | vCPU | RAM | Disks |
|---|---|---|---|---|
| `moni-app` (C, Monicomm) | `192.168.108.140` | per `PROJECT.md` §8 (GPU passthrough/vGPU if the LLM needs it) | | |
| `moni-syslog` (A) | `192.168.108.141` | 4 | 8 GB | 40 GB OS + **separate data disk** for archive and buffer (start 500 GB, thin) |
| `moni-snmp` (B) | `192.168.108.142` | 4 | 8 GB | 40 GB OS + 100 GB data (trapd state, buffer, config snapshots) |

All three are on one port group / subnet (`192.168.108.0/24`), one VMXNET3 NIC each.

vSphere specifics:

- **Linux VM template:** build one hardened template (for example Ubuntu LTS or Rocky Linux) with Docker
  Engine and the Compose plugin installed from **offline packages** (`.deb`/`.rpm` in the bundle), chrony, and
  the host firewall. Clone A and B from it. Optionally export it as an OVA to carry into the closed network.
- **Time:** turn off VMware Tools periodic time sync and use chrony against the site NTP. Guest clocks
  drifting after vMotion or snapshot restore would break syslog correlation.
- **Availability:** vSphere HA restarts A and B on another ESXi host if one fails. That is enough for phase 1;
  app-level HA (§8) comes later. If pairs are added, use a VM-VM **anti-affinity** rule so both copies never sit on the same ESXi host.
- **Separation:** on the shared subnet, enforce it with the `moni-app` firewall rules in §2.5. If Monicomm
  later moves to its own VLAN, give its VM no vNIC on the device network and allow only TCP 6000/8443 between them.
- **Snapshots:** take one before every upgrade of a collector bundle. Don't keep them for long on the syslog VM (its data disk grows fast). Back up the archive disk with the site's normal backup.
- **Disk performance:** put the syslog data disk on storage that handles steady small writes. Thick provisioning is safer if the datastore is shared and tight on space.
- **Bonus:** ESXi hosts and vCenter can send their own syslog to `moni-syslog`
  (`esxcli system syslog config set --loghost=udp://192.168.108.141:514`, then `esxcli system syslog reload`)
  and SNMP to `moni-snmp`, so the virtual layer shows up in Monicomm too. vCenter API discovery for the Mapper
  (VMs, hosts, vSwitches) would also run from `moni-snmp`, since Monicomm is kept away from the management plane.

---

## 3. Syslog design (syslog server)

### 3.1 Formats to handle

| Source | Typical format | Notes |
|---|---|---|
| Cisco IOS / IOS-XE | `<189>123: host: *Nov 25 10:58:12.345 IST: %LINK-3-UPDOWN: Interface Gi1/0/1, changed state to down` | Sequence number, optional `*` (clock not synced), timestamp inside the message. Parse `%FACILITY-SEVERITY-MNEMONIC`. |
| Cisco IOS-XR | `RP/0/RSP0/CPU0:Nov 25 10:58:12.345 IST: ifmgr[123]: %PKT_INFRA-LINK-3-UPDOWN : Interface ...` | Node prefix (`RP/0/...`) and process name before the mnemonic. |
| Cisco NX-OS | `2026 Nov 25 10:58:12.345 IST: %ETHPORT-5-IF_DOWN_LINK_FAILURE: ...` | Same mnemonic idea, different header. |
| Junos (default) | `<28>Nov 25 10:58:12 r1 mib2d[1234]: SNMP_TRAP_LINK_DOWN: ifIndex 512, ...` | Event tag in capitals. |
| Junos `structured-data` | RFC 5424 with SD-ID `[junos@2636...]` | **Preferred.** Key/value fields, year and ms in the timestamp. |
| SRX traffic logs | RFC 5424 `RT_FLOW_SESSION_CREATE/CLOSE/DENY` | High volume, separate input (§6.4). |

### 3.2 Pipeline

1. The syslog server's Vector receives → stamps `received_at`, `source_ip`, `collector_id` → writes the
   raw line to the local archive (evidence, `PROJECT.md` AI rule 4).
2. It parses the header (RFC 3164 or 5424) and forwards JSON to Monicomm's `ingest` over mTLS.
3. If Monicomm is unreachable, the disk buffer holds the data (size it for at least 24 h at peak rate).
   Buffer fill level and dropped counts are exported so the Dashboard can show collector health.
4. Monicomm `ingest` → Redis stream `ingest:syslog` → worker maps `source_ip` to `device_id`,
   extracts the vendor event code, normalizes it, inserts into a Timescale hypertable `syslog_events`.

Parsing vendor messages into event types happens in **Monicomm's worker**, not on the collector.
That keeps the collector simple and stable, and parser changes ship with Monicomm.

### 3.3 Normalized event types (starter list)

| Event | Cisco | Juniper |
|---|---|---|
| `link_down` / `link_up` | `%LINK-3-UPDOWN`, `%LINEPROTO-5-UPDOWN`, XR `%PKT_INFRA-LINK-3-UPDOWN` | `SNMP_TRAP_LINK_DOWN` / `_UP` |
| `config_change` | `%SYS-5-CONFIG_I`, `%PARSER-5-CFGLOG_LOGGEDCMD`, XR `%MGBL-CONFIG-6-DB_COMMIT` | `UI_COMMIT`, `UI_COMMIT_COMPLETED`, `UI_CMDLINE_READ_LINE` |
| `login_failed` | `%SEC_LOGIN-4-LOGIN_FAILED` | `SSHD_LOGIN_FAILED`, `LOGIN_FAILED` |
| `bgp_state` | `%BGP-5-ADJCHANGE`, `%BGP-3-NOTIFICATION` | `RPD_BGP_NEIGHBOR_STATE_CHANGED` |
| `ospf_state` | `%OSPF-5-ADJCHG` | `RPD_OSPF_NBRDOWN` / `NBRUP` |
| `isis_state` | `%CLNS-5-ADJCHANGE`, XR `%ROUTING-ISIS-5-ADJCHANGE` | `RPD_ISIS_ADJDOWN` / `ADJUP` |
| `vpn_tunnel` | `%CRYPTO-*` | `KMD_VPN_DOWN_ALARM_USER` / `KMD_VPN_UP_ALARM_USER` |
| `cluster_failover` | `%HA_EM-*`, redundancy `%REDUNDANCY-*` | `JSRPD_*` (SRX chassis cluster) |
| `stp_change` | `%SPANTREE-*` | STP messages (check per platform) |
| `hw_env` | `%ENVMON-*`, `%PLATFORM-*` | `CHASSISD_*` |

Unknown codes are kept as `other` with the raw code. The Analyzer's log clustering groups them later.

### 3.4 Retention (**DECIDE**, `PROJECT.md` open question 7)

- Parsed events in Monicomm: hot 30 days, Timescale compression after 7 days.
- Raw archive on the syslog server: gzip files, 1 year (or the unit's policy).
- SRX traffic logs: much shorter (for example 7 days), or not stored by default.

---

## 4. SNMP design (SNMP server)

### 4.1 Version and crypto (common denominator for Cisco and Juniper)

- **SNMPv3, `authPriv`, SHA (SHA-1) + AES-128.** Every IOS, IOS-XE, IOS-XR, NX-OS and Junos version
  in use supports this. Use SHA-2 only where every device supports it. Check in the lab.
- v2c only for legacy devices that can't do v3: read-only, behind an ACL, listed as an exception.

### 4.2 Polling (Telegraf): all devices

| Data | MIB / OID | Interval | Used by |
|---|---|---|---|
| Identity | SNMPv2-MIB `sysName`, `sysDescr`, `sysObjectID`, `sysUpTime` | 5 min | Inventory (vendor/model from sysObjectID) |
| Interfaces | IF-MIB `ifXTable` (HC 64-bit counters), `ifOperStatus`, `ifAdminStatus`, errors, discards | 60 s | Dashboard, Analyzer |
| Inventory | ENTITY-MIB `entPhysicalTable` (serials, modules, PSUs, optics) | 1 h | Mapper / documentation tool |
| Neighbors | LLDP-MIB (both vendors), CISCO-CDP-MIB (Cisco) | 5 min | Mapper topology |
| ARP | IP-MIB `ipNetToPhysicalTable` (fallback `ipNetToMediaTable`) | 5 min | Mapper (IP ↔ MAC) |
| CPU / memory | Cisco: CISCO-PROCESS-MIB `cpmCPUTotal5minRev`, CISCO-MEMORY-POOL / ENHANCED-MEMPOOL · Juniper: JUNIPER-MIB `jnxOperatingCPU`, `jnxOperatingBuffer` | 60 s | Dashboard, anomalies |
| Environment | Cisco: CISCO-ENVMON-MIB / CISCO-ENTITY-SENSOR-MIB · Juniper: `jnxOperatingTemp`, `jnxOperatingState` | 5 min | Dashboard |

### 4.3 Extra polling: switches

| Data | MIB | Interval |
|---|---|---|
| MAC table | BRIDGE-MIB / Q-BRIDGE-MIB `dot1qTpFdbTable` | 5 min |
| VLANs | Q-BRIDGE-MIB, CISCO-VTP-MIB (Cisco) | 15 min |

**Cisco MAC-table gotcha:** on Catalyst the MAC table is per VLAN. With v3 you query context
`vlan-<id>`, so the SNMP group needs `context vlan- match prefix` (template below). Without it the
MAC table comes back empty.

### 4.4 Extra polling: routers

| Data | MIB | Interval |
|---|---|---|
| BGP peers (state, uptime, prefixes) | Cisco: CISCO-BGP4-MIB `cbgpPeer2Table` (IPv4 + IPv6) · Juniper: BGP4-V2-MIB-JUNIPER `jnxBgpM2PeerTable` · fallback BGP4-MIB `bgpPeerTable` (IPv4 only) | 60 s |
| OSPF neighbors | OSPF-MIB `ospfNbrTable` (OSPFv3-MIB for IPv6) | 60 s |
| IS-IS adjacencies | ISIS-MIB `isisISAdjTable` | 60 s |
| Route count | IP-FORWARD-MIB `inetCidrRouteNumber` (**count only**) | 5 min |
| VRFs | Cisco: MPLS-L3VPN-STD-MIB `mplsL3VpnVrfTable` · Juniper: routing instances via context | 15 min |
| IPsec tunnels | Cisco: CISCO-IPSEC-FLOW-MONITOR-MIB · Juniper: JUNIPER-IPSEC-FLOW-MON-MIB | 60 s |
| QoS drops (optional) | Cisco: CISCO-CLASS-BASED-QOS-MIB · Juniper: JUNIPER-COS-MIB | 5 min |

Router rules:

- **Never walk the routing table** (`inetCidrRouteTable` / `ipCidrRouteTable`). A full BGP table is
  hundreds of thousands of rows: slow, and it can load the route processor. Poll the count, and get
  specific routes on demand (configurator read API or NETCONF) when an investigation needs them.
- **VRFs:** ARP, BGP and OSPF data inside a VRF needs an SNMP context mapped to that VRF (Cisco) or a
  routing-instance context (Junos). Add the mappings once we have the VRF list.
- **Interface counts:** big routers have thousands of sub-interfaces. Poll `ifXTable` with bulk walks,
  and filter by interface type/name per poll profile.

### 4.5 Extra polling: firewalls (Juniper SRX)

| Data | MIB | Interval |
|---|---|---|
| Sessions, SPU CPU/memory | JUNIPER-SRX5000-SPU-MONITORING-MIB (`jnxJsSPUMonitoring*`), JUNIPER-JS-POLICY / flow MIBs | 60 s |
| Chassis cluster state | JUNIPER-CHASSIS-CLUSTER-MIB | 60 s |

On an SRX cluster, poll each node on its own `fxp0` address.

### 4.6 Traps vs informs

| | Traps | Informs (**recommended**) |
|---|---|---|
| Delivery | Fire and forget, lost if the server is down | Acknowledged and retried |
| v3 engine ID | Receiver must know **each device's** engine ID | Device must know the **receiver's** engine ID (one value for all devices) |

Plan: **informs** everywhere they're supported, traps as a fallback.
`trapd` must keep a **fixed engine ID** (`/var/lib/net-snmp` on a named volume). Record the value in
the device templates. If it changes, informs from every device break.

Traps to enable: linkUp/linkDown, coldStart/warmStart, authenticationFailure, config change,
entity/FRU, environment, CPU threshold. Routers also: BGP (backward transition), OSPF state, IS-IS
adjacency, IPsec tunnel up/down. SRX also: chassis cluster failover.

### 4.7 MIBs (offline)

- Download on the build machine: Cisco MIBs for the exact platforms (IOS-XE, IOS-XR, NX-OS) and the
  Juniper MIB package for each Junos release in use.
- Ship in the SNMP server bundle as a `mibs` volume, with a checksum. Telegraf (gosmi) and snmptrapd load them.
- Nothing fetches MIBs at runtime.

---

## 5. Device templates (onboarding)

Apply with the existing change process: one device first, then a pilot group, then everything. Each
template sets NTP, timestamps, source interface, syslog host (**192.168.108.141**), SNMPv3 read user,
and the inform target (**192.168.108.142**).

### 5.1 Cisco IOS / IOS-XE (switches and routers: Catalyst, ISR, ASR 1000, Catalyst 8000)

```
! --- time and log format ---
ntp server <ntp-ip>
clock timezone IST 2 0
service timestamps log datetime msec localtime show-timezone year
service sequence-numbers
!
! --- syslog ---
logging origin-id hostname
logging source-interface Loopback0              ! add "vrf Mgmt-vrf" if logging via the mgmt VRF
logging host 192.168.108.141 transport udp port 514 ! tcp is also supported; TLS on newer IOS-XE
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
 permit 192.168.108.142
snmp-server view MONI-RO iso included
snmp-server group MONI-RO-GRP v3 priv read MONI-RO access MONI-SNMP
snmp-server group MONI-RO-GRP v3 priv context vlan- match prefix read MONI-RO access MONI-SNMP  ! switches only
snmp-server user moni-poll MONI-RO-GRP v3 auth sha <AUTH> priv aes 128 <PRIV> access MONI-SNMP
snmp-server ifindex persist
snmp-server trap-source Loopback0
!
! --- informs (needs the SNMP server's engine ID) ---
snmp-server engineID remote 192.168.108.142 <TRAPD_ENGINE_ID_HEX>
snmp-server user moni-trap MONI-RO-GRP remote 192.168.108.142 v3 auth sha <AUTH> priv aes 128 <PRIV>
snmp-server host 192.168.108.142 informs version 3 priv moni-trap
snmp-server enable traps snmp linkdown linkup coldstart warmstart authentication
snmp-server enable traps config
snmp-server enable traps entity
snmp-server enable traps envmon
snmp-server enable traps cpu threshold
! routers:
snmp-server enable traps bgp
snmp-server enable traps ospf state-change
snmp-server enable traps ipsec tunnel start stop
```

`archive path` is also what makes `configure terminal revert timer` and `configure replace` work (phase F rollback).

### 5.2 Cisco IOS-XR (ASR 9000, NCS, 8000 series)

IOS-XR syntax is different. This template is a **starting point to verify in the lab**, especially
the inform/remote-user lines. Start with traps on XR if informs give trouble.

```
ntp server <ntp-ip>
clock timezone IST Asia/Jerusalem
service timestamps log datetime localtime msec show-timezone year
!
logging 192.168.108.141 vrf default severity info port default
logging source-interface Loopback0
logging hostnameprefix <hostname>
!
snmp-server view MONI-RO 1.3.6.1 included
snmp-server group MONI-RO-GRP v3 priv read MONI-RO
snmp-server user moni-poll MONI-RO-GRP v3 auth sha clear <AUTH> priv aes 128 clear <PRIV>
snmp-server ifindex persist
snmp-server trap-source Loopback0
snmp-server host 192.168.108.142 traps version 3 priv moni-trap
snmp-server traps snmp linkup
snmp-server traps snmp linkdown
snmp-server traps config
snmp-server traps bgp
snmp-server traps ospf state-change neighbor-state-change
snmp-server traps entity
```

Restrict SNMP to the SNMP server with an ACL or a management-plane protection (MPP) rule.
Use `vrf <mgmt-vrf>` on the `logging` and `snmp-server host` lines if management runs in a VRF.

### 5.3 Juniper Junos (EX / QFX switches, MX routers, SRX firewalls)

```
# --- time and log format ---
set system ntp server <ntp-ip>
set system time-zone Asia/Jerusalem
set system syslog time-format year millisecond
#
# --- syslog (RFC 5424 structured data) ---
set system syslog host 192.168.108.141 any info
set system syslog host 192.168.108.141 authorization info
set system syslog host 192.168.108.141 interactive-commands info
set system syslog host 192.168.108.141 change-log info
set system syslog host 192.168.108.141 structured-data
set system syslog host 192.168.108.141 source-address 10.0.0.1
# if management-instance is enabled:
# set system syslog host 192.168.108.141 routing-instance mgmt_junos
#
# --- SNMPv3 read-only ---
set snmp engine-id use-mac-address
set snmp view MONI-ALL oid .1 include
set snmp v3 usm local-engine user moni-poll authentication-sha authentication-password "<AUTH>"
set snmp v3 usm local-engine user moni-poll privacy-aes128 privacy-password "<PRIV>"
set snmp v3 vacm security-to-group security-model usm security-name moni-poll group MONI-RO
set snmp v3 vacm access group MONI-RO default-context-prefix security-model usm security-level privacy read-view MONI-ALL
#
# --- informs to the SNMP server ---
set snmp v3 usm remote-engine <TRAPD_ENGINE_ID_HEX> user moni-trap authentication-sha authentication-password "<AUTH>"
set snmp v3 usm remote-engine <TRAPD_ENGINE_ID_HEX> user moni-trap privacy-aes128 privacy-password "<PRIV>"
set snmp v3 target-address MONI address 192.168.108.142
set snmp v3 target-address MONI port 162
set snmp v3 target-address MONI tag-list moni-tag
set snmp v3 target-address MONI target-parameters MONI-TP
set snmp v3 target-parameters MONI-TP parameters message-processing-model v3 security-model usm security-level privacy security-name moni-trap
set snmp v3 target-parameters MONI-TP notify-filter MONI-NF
set snmp v3 notify MONI-N type inform tag moni-tag
set snmp v3 notify-filter MONI-NF oid .1 include
set snmp trap-options source-address 10.0.0.1
```

Per platform:

- **All:** restrict SNMP with a firewall filter on `lo0` (or the mgmt interface) that allows only `192.168.108.142` on UDP 161.
- **MX routers:** `default-context-prefix` above lets the poller read routing-instance data through SNMP contexts.
- **SRX cluster:** each node uses its own `fxp0` address as the source. Poll and receive from both nodes.

### 5.4 Onboarding checklist per device

- [ ] Clock synced (`show ntp status` / `show ntp associations`)
- [ ] Test syslog arrives (`send log 7 "moni test"` on IOS/IOS-XE; `logger -e TEST "moni test"` from the Junos shell)
- [ ] `snmpwalk -v3 -l authPriv ... sysName` from the SNMP server works
- [ ] A test inform/trap arrives (shut/no shut a spare port, or Cisco `test snmp trap ...` / Junos `request snmp spoof-trap linkDown ...`)
- [ ] The device appears in Monicomm with the right vendor, model, role and interfaces
- [ ] Routers: BGP/OSPF peers appear with the right state

---

## 6. Router- and firewall-specific notes

### 6.1 Management path

Many routers are managed **in-band** (through a loopback reached over the routed network), not
through a dedicated management port. Then any change to routing or to the interface you manage
through can cut off syslog, SNMP and the configurator itself. That's why every router change
requires confirmed commit with auto-rollback (§7.2).

### 6.2 Source addresses

Always send from a stable address: `Loopback0` on Cisco, `lo0` address on Junos routers, `fxp0`
on SRX cluster nodes. Otherwise the device shows up under whichever interface IP the packet left from.

### 6.3 Volume

Routers with many peers and sub-interfaces produce more syslog and traps than switches, especially
during a routing event (one link failure can mean hundreds of BGP/OSPF messages in seconds). Size the
syslog server disk buffer and the Monicomm worker for these bursts, not for the average.

### 6.4 SRX traffic (session) logs

These are separate from system syslog, come from the data plane, and can be thousands of messages
per second. Default: **off**. If the team wants them:

```
set security log mode stream
set security log format sd-syslog
set security log source-address 10.0.0.1
set security log stream MONI-FLOW host 192.168.108.141
set security log stream MONI-FLOW host port 5514
# and on the policies to log: then log session-close
```

They arrive on a separate port (UDP 5514) so they get their own rate limit, buffer and short retention,
and never delay normal syslog.

---

## 7. Configuring devices from the SNMP server (phase F)

### 7.1 What SNMP can and can't do

| Operation | Cisco via SNMP SET | Juniper via SNMP SET |
|---|---|---|
| Port shut / no shut | ✅ IF-MIB `ifAdminStatus` (switches; on routers use NETCONF so it can roll back) | ❌ → NETCONF |
| Port description | ✅ IF-MIB `ifAlias` | ❌ → NETCONF |
| Access VLAN on a switch port | ✅ CISCO-VLAN-MEMBERSHIP-MIB `vmVlan` | ❌ → NETCONF |
| Back up running config | ✅ CISCO-CONFIG-COPY-MIB → SCP/SFTP | ❌ → NETCONF `get-config` |
| Push config | ⚠️ CONFIG-COPY to running (merges, doesn't replace; risky) | ❌ |
| Routing, ACL, firewall policy changes | ❌ not practical | ❌ |
| Commit with auto-rollback | ❌ | ❌ |

Junos allows SET only on a few utility MIBs (ping, traceroute, jnxUtil, SNMP config tables). Check your
version, but don't plan on SNMP to configure Juniper.

**Recommendation (DECIDE):** the `configurator` on the SNMP server uses:

- **SNMP SET** only for quick Cisco **switch-port** operations (shut/no shut, description, access VLAN), and
- **NETCONF** (TCP 830) for everything else: all router and firewall changes and all Juniper changes.
  Junos supports it natively. IOS-XE with `netconf-yang` + candidate datastore. IOS-XR natively, with commit/rollback.
- SSH/CLI (scrapli) as the fallback for old IOS without NETCONF.

### 7.2 Change flow (matches the slide: preview → approve → apply → one-click rollback)

1. **Snapshot:** the configurator fetches the running config. A copy is stored on the SNMP server and in Monicomm (versioned).
2. **Preview:** Monicomm shows the exact diff (or the OIDs and values for a SET) plus the impact analyzer
   output: affected ports/VLANs (switches); affected peers, routes and the management path (routers);
   affected policies and zones (firewalls); and current traffic on those links.
3. **Approve:** a technician with the `admin` (or new `operator`) role approves in Monicomm. A second
   approver is **required** for routers, firewalls and core switches.
4. **Apply with a safety net** (the configurator does this):
   - Junos: `commit confirmed 5` over NETCONF.
   - IOS-XR: `commit confirmed 300` over NETCONF/CLI.
   - IOS-XE NETCONF: confirmed commit on the candidate datastore.
   - Classic IOS CLI: `configure terminal revert timer 5`, then `configure confirm`.
   - Cisco SNMP SET (switch ports only): store the previous value and write it back on rollback.
5. **Verify:** for 2–5 minutes, watch SNMP and syslog for the device (links, errors, routing peers,
   reachability of the device itself). Healthy → confirm. Not healthy, or nobody confirms → the device rolls back by itself.
6. **Rollback button** any time later: Junos `rollback N`; IOS-XR `rollback configuration last 1`;
   IOS/IOS-XE `configure replace flash:archive/cfg-N`; SNMP restores the stored previous value.
7. **Audit** on both sides: who, approval ID, what, when, diff, result and rollback point.

### 7.3 Rules this must respect

- `CLAUDE.md` rule 3 and `PROJECT.md` §3 AI rule 3: **AI tools stay read-only.** The chat assistant
  ("ChatIAF") can explain a change, predict impact and draft it, but can't apply it. It runs on the
  Monicomm host, which is firewalled off from devices. Only an approved request through Monicomm's approval UI
  can call the configurator, and the LLM has no tool that reaches that API.
- The configurator rejects any request without a valid approval ID, and logs everything locally even if Monicomm is lost.
- Write credentials (Cisco `MONI-RW` group, NETCONF user) exist only in the configurator.
- This needs its own ADR, a security review and sign-off from the network owners before any write credential is created on a production device.

Cisco write user, restricted to the OIDs we SET:

```
ip access-list standard MONI-SNMP-RW
 permit 192.168.108.142
snmp-server view MONI-RW 1.3.6.1.2.1.2.2.1.7 included          ! ifAdminStatus
snmp-server view MONI-RW 1.3.6.1.2.1.31.1.1.1.18 included      ! ifAlias
snmp-server view MONI-RW 1.3.6.1.4.1.9.9.68.1.2.2.1.2 included ! vmVlan
snmp-server view MONI-RW 1.3.6.1.4.1.9.9.96 included           ! CISCO-CONFIG-COPY-MIB
snmp-server group MONI-RW-GRP v3 priv read MONI-RO write MONI-RW access MONI-SNMP-RW
snmp-server user moni-cfg MONI-RW-GRP v3 auth sha <AUTH> priv aes 128 <PRIV> access MONI-SNMP-RW
snmp-server file-transfer access-group MONI-SNMP-RW protocol scp
```

---

## 8. High availability (optional, later)

- **Syslog:** devices can send to two syslog servers (second `logging host` / `syslog host` line).
  Monicomm drops duplicates by `(device, timestamp, sequence/hash)`.
- **Traps:** devices can send informs to two targets.
- **Polling and configurator:** active/standby only (two pollers would double the SNMP load on devices).
- Start with one syslog server and one SNMP server. Add HA once the volume and the unit's availability requirement are known.

---

## 9. Lab and testing (no real network needed)

| Need | Tool (all offline, in the bundles) |
|---|---|
| Fake SNMP devices | **snmpsim**: record `snmpwalk`s from real Cisco/Juniper switches, routers and SRX once (`.snmprec`) and replay them as many agents |
| Real OS behavior | **containerlab** (or GNS3/EVE-NG) with vJunos-switch / vJunos-router / vSRX and Cisco IOL / Cat8000v / XRd. Licensed images come in on approved media. |
| Syslog load | `logger` / `loggen` replaying captured Cisco, IOS-XR and Junos lines at the target EPS, including a "routing storm" burst |
| Trap tests | `snmptrap` / `snmpinform` from net-snmp, plus real link and BGP-peer flaps in the lab |
| Separation check | Monicomm host cannot reach the lab devices on 161/22/23/830; everything still works through the collectors |
| Air-gap check | All three hosts with outbound internet removed |

Test cases: each sample line in §3.3 parses to the right event; a 3164 line without a year gets the right
year; a clock-unsynced Cisco line (`*`) is flagged; 2× target EPS for 10 minutes with zero drops;
**Monicomm down for 1 hour → collectors buffer and catch up with no loss**; trapd restart keeps the
engine ID; v3 wrong password is rejected and logged; configurator rejects a request without an approval
ID; a router change that breaks the management path rolls back by itself.

---

## 10. Air-gapped delivery (`deploy/offline/`)

Three bundles, each with its own `docker-compose.yml`, `.env.example`, install script and SHA-256 checksums:

| Bundle | Contents |
|---|---|
| `monicomm` | Existing stack + new `ingest` (Vector) service |
| `syslog-server` | Vector image, Vector config, cert install script |
| `snmp-server` | trapd image (Debian + net-snmp), Telegraf image, configurator image + Python wheels (pysnmp, ncclient, scrapli), Vector image, MIB bundle, cert install script |

Plus: device templates (§5) as text files, a script that creates the internal CA and the
per-host mTLS certificates, and offline Docker Engine + Compose packages for the VM template (§2.7).
Every image pinned by tag **and** digest.

---

## 11. Rollout phases

| Phase | Work | Done when |
|---|---|---|
| **A. Decide + lab** | ADR for the separate deployments and tools; collect device models and OS versions; build the VM template and the `moni-syslog` / `moni-snmp` VMs on vSphere; build the lab (switch, router, SRX per vendor) | ADR merged; VMs up; lab reachable from the collector VMs only |
| **B. Syslog server** | Vector receive + archive + forward; Monicomm `ingest`; parser + normalization | Lab logs reach Monicomm parsed; load test and "Monicomm down 1 h" test pass |
| **C. Traps** | `trapd` with fixed engine ID, MIB decoding, shipped through the SNMP server's Vector | Informs from both vendors arrive and decode to names |
| **D. Polling** | Target-list API, Telegraf profiles per role (switch / router / firewall) | Interfaces, CPU/mem, LLDP/CDP, MAC/ARP and BGP/OSPF data for lab devices |
| **E. Onboarding** | Templates on a pilot group (switches first, then routers, then firewalls), then all | Every device passes §5.4 |
| **F. Configure** | Configurator API, approval UI, preview/impact, confirmed commit, rollback, audit | Lab: switch, router and SRX changes apply, auto-roll back on failure, and manually roll back, on both vendors |

A–E are read-only and safe. F touches device config and goes last, behind its own review.

---

## 12. Open questions (add to `PROJECT.md` §11)

1. Device list: which Cisco families (IOS, IOS-XE, IOS-XR, NX-OS, ASA/FTD) and Juniper families (EX, QFX, MX, SRX), and which OS versions?
2. How are routers managed: out-of-band, mgmt VRF or in-band? Which subnets?
3. vSphere (§2.7): which cluster and datastore? Keep the flat `192.168.108.0/24` or move Monicomm to its own VLAN later? Is vSphere HA enough or is app-level HA needed?
4. Is there an NTP server inside the closed network? An internal CA for the mTLS certificates?
5. Can every device do SNMPv3 with SHA + AES-128? Any v2c-only legacy devices?
6. Expected syslog volume (average and burst) and number of devices per role.
7. SRX traffic logs: wanted at all? If yes, retention?
8. Is TLS syslog (6514) required, or is UDP/TCP on the mgmt network acceptable?
9. Are write actions on devices approved? By whom? Which devices are excluded (core routers, crypto)?
10. Is NETCONF allowed (`netconf-yang` on IOS-XE, `set system services netconf ssh` on Junos, `netconf-yang agent ssh` on IOS-XR)?
11. Retention for parsed events and the raw syslog archive.
