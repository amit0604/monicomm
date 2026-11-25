# collector/: syslog server and SNMP server

Separate Docker deployments that run on their own VMs on the device management network, apart from
the Monicomm stack. Design: `docs/plans/syslog-snmp-deployment.md`. Setup: `docs/runbooks/collector-servers-setup.md`.
Sending to, querying and watching the servers: `docs/runbooks/talking-to-collectors.md`.

```
collector/
├── syslog-server/     Vector: UDP/TCP 514 → raw archive + forward to Monicomm (mTLS)
├── snmp-server/       trapd (net-snmp) + poller (Telegraf, SNMPv3) + shipper (Vector) → Monicomm (mTLS)
│   └── snmpq          ad-hoc read-only SNMP (get/walk/test-inform/poll-test) with the stored credentials
├── dev-ingest/        temporary stand-in for Monicomm `ingest` (TCP 6000, mTLS) that writes JSON files
├── pki/make-certs.sh  internal CA + mTLS certificates
├── certs/             this VM's certificates (git-ignored)
└── test/e2e.sh        end-to-end test on one Docker host, no real devices
```

## Event contract (collectors → Monicomm `ingest`)

Transport: Vector-to-Vector protocol on TCP 6000, mutual TLS (client certs from `pki/`). Every event is
a JSON object with `schema`, `kind` and `collector_id`. Changing a schema means a new version (`.v2`) and an update here and in `PROJECT.md`.

**`monicomm.syslog.v1`** (`kind: syslog`)

| Field | Type | Notes |
|---|---|---|
| `collector_id` | string | e.g. `moni-syslog-01` |
| `source_ip` | string | UDP/TCP peer address = the device (use this, not the hostname in the message) |
| `received_at` | timestamp (UTC) | when the collector received it |
| `raw` | string | the line as received; the same line is in the raw archive |
| `syslog` | object | header parsed by Vector `parse_syslog` (`facility`, `severity`, `hostname`, `appname`, `procid`, `msgid`, `timestamp`, `message`, structured data). Missing when parsing failed. |
| `parse_error` | string | present only when the header couldn't be parsed |

Vendor parsing (Cisco `%FAC-SEV-MNEMONIC`, Junos event tags) is Monicomm's job (plan §3.3).

**`monicomm.trap.v1`** (`kind: trap`)

| Field | Type | Notes |
|---|---|---|
| `collector_id`, `source_ip`, `received_at` | | as above |
| `trap_oid` | string | numeric, e.g. `.1.3.6.1.6.3.1.1.5.3` (linkDown) |
| `device_uptime` | string | sysUpTime varbind as printed by net-snmp |
| `varbinds` | array of `{oid, value}` | numeric OIDs; values as printed by net-snmp. MIB name translation happens in Monicomm. |
| `transport` | string | snmptrapd's transport line |

**`monicomm.snmp_metric.v1`** (`kind: snmp_metric`)

| Field | Type | Notes |
|---|---|---|
| `collector_id`, `source_ip` | | `source_ip` = polled device |
| `measurement` | string | `snmp_system`, `snmp_interface`, `snmp_identity`, `snmp_lldp_neighbor`, `snmp_arp`, `snmp_entity`, `snmp_cisco_*`, `snmp_cdp_neighbor`, `snmp_juniper_operating`, `snmp_bgp_peer`, `snmp_ospf_neighbor` |
| `tags` | object | `source` (polled device IP), `sysName`, `index` (table row index), plus tag columns (`ifName`, `descr`...) |
| `fields` | object | counter/gauge/string values named after the MIB object |
| `polled_at` | integer | Unix ms |

**Collector health** (Vector metric events, not logs): `component_*_events_total`, `buffer_*`, tagged `collector_id`.

## Not here yet

- `configurator` (device writes, plan §7): phase F, needs its own ADR and security review first.
- Target-list API: the poller reads `snmp-server/inventory/devices.csv` until Monicomm's inventory API exists.
- Cisco per-VLAN MAC tables (needs SNMP context per VLAN): part of the Mapper's discovery job.
- IPv6/VRF BGP peers (vendor BGP MIBs), SRX SPU and cluster MIBs: add after lab validation.
- TLS syslog (6514): commented out in `syslog-server/vector/vector.yaml` until the policy decision.
