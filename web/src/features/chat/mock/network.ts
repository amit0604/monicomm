// Mock network for the ChatIAF prototype. Small on purpose: one site, Cisco + Juniper,
// shaped like what the SNMP poller and syslog pipeline will store (docs/plans/syslog-snmp-deployment.md).
import type { DeviceRole } from "../types";

export interface Device {
  name: string;
  role: DeviceRole;
  vendor: "Cisco" | "Juniper";
  model: string;
  mgmtIp: string;
  site: string;
  status: "up" | "down";
}

export interface Interface {
  device: string;
  name: string;
  description: string;
  admin: "up" | "down";
  oper: "up" | "down" | "err-disabled";
  mode: "access" | "trunk" | "routed";
  vlan: string;
  speed: string;
  utilization: number;
  errors24h: number;
  neighbor?: string;
  activeHosts: number;
  carriesMgmt?: boolean;
  reason?: string;
}

export interface LogLine {
  time: string;
  device: string;
  severity: "emerg" | "alert" | "crit" | "err" | "warning" | "notice" | "info" | "debug";
  message: string;
}

export interface Alert {
  id: string;
  severity: "critical" | "warning" | "info";
  device: string;
  title: string;
  since: string;
}

export interface ConfigChange {
  time: string;
  device: string;
  user: string;
  summary: string;
  diff: string;
}

export interface Host {
  ip: string;
  mac: string;
  hostname: string;
  device: string;
  port: string;
  vlan: string;
}

export const DEVICES: Device[] = [
  {
    name: "core-sw-01",
    role: "core-switch",
    vendor: "Cisco",
    model: "C9500-48Y4C",
    mgmtIp: "10.0.0.1",
    site: "HQ",
    status: "up",
  },
  {
    name: "dist-sw-01",
    role: "distribution-switch",
    vendor: "Cisco",
    model: "C9300-48UXM",
    mgmtIp: "10.0.0.11",
    site: "HQ",
    status: "up",
  },
  {
    name: "access-sw-12",
    role: "access-switch",
    vendor: "Cisco",
    model: "C9200L-48P-4G",
    mgmtIp: "10.0.0.112",
    site: "HQ",
    status: "up",
  },
  {
    name: "edge-rtr-01",
    role: "router",
    vendor: "Juniper",
    model: "MX204",
    mgmtIp: "10.0.0.254",
    site: "HQ",
    status: "up",
  },
  {
    name: "fw-01",
    role: "firewall",
    vendor: "Juniper",
    model: "SRX345",
    mgmtIp: "10.0.0.253",
    site: "HQ",
    status: "up",
  },
];

export const INTERFACES: Interface[] = [
  {
    device: "access-sw-12",
    name: "Gi1/0/5",
    description: "LAB-05 desk",
    admin: "up",
    oper: "err-disabled",
    mode: "access",
    vlan: "30",
    speed: "1G",
    utilization: 0,
    errors24h: 0,
    activeHosts: 0,
    reason: "bpduguard",
  },
  {
    device: "access-sw-12",
    name: "Gi1/0/12",
    description: "Printer 2nd floor",
    admin: "up",
    oper: "up",
    mode: "access",
    vlan: "20",
    speed: "1G",
    utilization: 2,
    errors24h: 0,
    activeHosts: 1,
  },
  {
    device: "access-sw-12",
    name: "Gi1/0/48",
    description: "UPLINK to dist-sw-01 Te1/1/3",
    admin: "up",
    oper: "up",
    mode: "trunk",
    vlan: "10,20,30,99",
    speed: "1G",
    utilization: 41,
    errors24h: 0,
    neighbor: "dist-sw-01 Te1/1/3",
    activeHosts: 37,
    carriesMgmt: true,
  },
  {
    device: "core-sw-01",
    name: "Po1",
    description: "to dist-sw-01",
    admin: "up",
    oper: "up",
    mode: "trunk",
    vlan: "10,20,30,99",
    speed: "20G",
    utilization: 63,
    errors24h: 0,
    neighbor: "dist-sw-01 Po1",
    activeHosts: 212,
    carriesMgmt: true,
  },
  {
    device: "edge-rtr-01",
    name: "xe-0/1/0",
    description: "WAN-A to Site-North",
    admin: "up",
    oper: "up",
    mode: "routed",
    vlan: "-",
    speed: "10G",
    utilization: 92,
    errors24h: 1840,
    neighbor: "north-rtr-01 xe-0/1/0",
    activeHosts: 0,
  },
  {
    device: "edge-rtr-01",
    name: "xe-0/1/1",
    description: "WAN-B to Site-North (backup)",
    admin: "up",
    oper: "up",
    mode: "routed",
    vlan: "-",
    speed: "10G",
    utilization: 8,
    errors24h: 0,
    neighbor: "north-rtr-01 xe-0/1/1",
    activeHosts: 0,
  },
];

export const LOGS: LogLine[] = [
  {
    time: "09:41:07",
    device: "access-sw-12",
    severity: "err",
    message:
      "%SPANTREE-2-BLOCK_BPDUGUARD: Received BPDU on port Gi1/0/5 with BPDU Guard enabled. Disabling port.",
  },
  {
    time: "09:41:07",
    device: "access-sw-12",
    severity: "err",
    message:
      "%PM-4-ERR_DISABLE: bpduguard error detected on Gi1/0/5, putting Gi1/0/5 in err-disable state",
  },
  {
    time: "09:41:08",
    device: "access-sw-12",
    severity: "notice",
    message: "%LINK-3-UPDOWN: Interface GigabitEthernet1/0/5, changed state to down",
  },
  {
    time: "09:40:51",
    device: "access-sw-12",
    severity: "info",
    message:
      "%LLDP-6-NEIGHBOR_ADD: New neighbor on Gi1/0/5: chassis TP-Link TL-SG105 (unmanaged switch)",
  },
  {
    time: "07:12:33",
    device: "edge-rtr-01",
    severity: "warning",
    message:
      "SNMP_TRAP_LINK_DOWN: ifIndex 545, ifAdminStatus up(1), ifOperStatus down(2), ifName xe-0/1/0",
  },
  {
    time: "07:12:35",
    device: "edge-rtr-01",
    severity: "notice",
    message:
      "SNMP_TRAP_LINK_UP: ifIndex 545, ifAdminStatus up(1), ifOperStatus up(1), ifName xe-0/1/0",
  },
  {
    time: "07:12:41",
    device: "edge-rtr-01",
    severity: "warning",
    message:
      "RPD_OSPF_NBRDOWN: OSPF neighbor 10.255.0.2 (realm ospf-v2 xe-0/1/0.0 area 0.0.0.0) state changed from Full to Init",
  },
];

export const ALERTS: Alert[] = [
  {
    id: "AL-2291",
    severity: "critical",
    device: "edge-rtr-01",
    title: "xe-0/1/0 CRC errors rising (1,840 in 24h), utilization 92%",
    since: "07:12",
  },
  {
    id: "AL-2290",
    severity: "warning",
    device: "access-sw-12",
    title: "Gi1/0/5 err-disabled (BPDU Guard)",
    since: "09:41",
  },
  {
    id: "AL-2287",
    severity: "warning",
    device: "core-sw-01",
    title: "VLAN 30 latency +38 ms after config change",
    since: "yesterday 23:14",
  },
  {
    id: "AL-2284",
    severity: "info",
    device: "fw-01",
    title: "Policy hit count spike: allow-dns-out",
    since: "yesterday 18:02",
  },
];

export const CONFIG_CHANGES: ConfigChange[] = [
  {
    time: "yesterday 23:08",
    device: "core-sw-01",
    user: "netops-dana",
    summary: "Allowed VLAN 30 on Po1 trunk",
    diff: ` interface Port-channel1
-  switchport trunk allowed vlan 10,20,99
+  switchport trunk allowed vlan 10,20,30,99`,
  },
  {
    time: "yesterday 23:10",
    device: "core-sw-01",
    user: "netops-dana",
    summary: "Raised OSPF cost on Vlan30 SVI",
    diff: ` interface Vlan30
-  ip ospf cost 10
+  ip ospf cost 200`,
  },
];

export const HOSTS: Host[] = [
  {
    ip: "10.1.4.22",
    mac: "00:1a:2b:3c:4d:5e",
    hostname: "PC-LAB-05",
    device: "access-sw-12",
    port: "Gi1/0/5",
    vlan: "30",
  },
  {
    ip: "10.1.2.40",
    mac: "3c:52:82:aa:10:07",
    hostname: "PRN-2F-02",
    device: "access-sw-12",
    port: "Gi1/0/12",
    vlan: "20",
  },
];
