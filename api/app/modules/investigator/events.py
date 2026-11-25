"""Normalize one collector JSONL line (monicomm.syslog.v1 / monicomm.trap.v1) into a NetEvent.

Vendor mapping follows docs/plans/syslog-snmp-deployment.md section 3.3 (collectors PR).
Pure functions: no I/O, no logging.
"""

import hashlib
import ipaddress
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class NetEvent:
    id: str
    type: str
    state: str | None
    device: str
    hostname: str | None
    interface: str | None
    peer: str | None
    severity: str
    ts: datetime
    code: str | None
    raw: str
    abnormal: bool


EVENT_TYPES = (
    "link",
    "config_change",
    "login_failed",
    "bgp",
    "ospf",
    "isis",
    "vpn",
    "cluster_failover",
    "stp_change",
    "hw_env",
    "other",
)
STATEFUL = {"link", "bgp", "ospf", "isis", "vpn"}
NO_INTERFACE = {"config_change", "login_failed"}  # "on vty0" is a session line, not a port
SEVERITIES = ("emerg", "alert", "crit", "err", "warning", "notice", "info", "debug")

# Cisco codes are stored as "FAC-SEV-MNEMONIC" (no "%"), Junos codes as the event tag.
CODE_TYPES = [
    (r"^(?:PKT_INFRA-)?(?:LINK|LINEPROTO)-\d-(?:UPDOWN|CHANGED)$", "link"),
    (r"^ETHPORT-\d-IF_(?:DOWN|UP)", "link"),
    (r"^SNMP_TRAP_LINK_(?:DOWN|UP)$", "link"),
    (r"^(?:SYS-\d-CONFIG_I|PARSER-\d-CFGLOG_LOGGEDCMD|MGBL-CONFIG-\d-DB_COMMIT)$", "config_change"),
    (r"^UI_(?:COMMIT|COMMIT_COMPLETED|CMDLINE_READ_LINE)$", "config_change"),
    (r"^(?:SEC_LOGIN-\d-LOGIN_FAILED|SSHD_LOGIN_FAILED|LOGIN_FAILED)$", "login_failed"),
    (r"^(?:ROUTING-)?BGP-\d-(?:ADJCHANGE|NOTIFICATION)$", "bgp"),
    (r"^RPD_BGP_NEIGHBOR_STATE_CHANGED$", "bgp"),
    (r"^(?:ROUTING-)?OSPF(?:V3)?-\d-(?:ADJCHG|NBRSTATE)$", "ospf"),
    (r"^RPD_OSPF_NBR(?:DOWN|UP)$", "ospf"),
    (r"^(?:CLNS|ROUTING-ISIS)-\d-ADJCHANGE$", "isis"),
    (r"^RPD_ISIS_ADJ(?:DOWN|UP)$", "isis"),
    (r"^CRYPTO-|^KMD_VPN_(?:DOWN|UP)_ALARM_USER$", "vpn"),
    (r"^REDUNDANCY-|^JSRPD_", "cluster_failover"),  # HA_EM is Cisco EEM, not HA
    (r"^SPANTREE-", "stp_change"),
    (r"^(?:ENVMON|PLATFORM|PLATFORM_ENV)-|^CHASSISD_", "hw_env"),
]

TAGS = (
    r"SNMP_TRAP_LINK_(?:DOWN|UP)|RPD_[A-Z0-9_]+|UI_[A-Z0-9_]+|SSHD_LOGIN_FAILED|LOGIN_FAILED"
    r"|KMD_[A-Z0-9_]+|JSRPD_[A-Z0-9_]+|CHASSISD_[A-Z0-9_]+"
)
# Codes count only at the start of the message (after a short header prefix), so text a user
# controls later in the line (an SSH username, a description) cannot fake an event.
# Allowed prefix: an optional "<PRI>" plus up to 4 header tokens (timestamp, host), then an
# optional run ending in ": " or "] " (seq no, "*Nov 25 10:00:00.1 UTC: ", XR "proc[pid]: ").
# No quotes or "%" in it, so a quoted username or a description cannot carry a code.
HEAD = r"^(?:<\d{1,3}>(?:[^\s%'\"]+\s+){0,4}?)?(?:[^%'\"]{0,100}?[:\]]\s)?"
CISCO_CODE = re.compile(HEAD + r"%((?:[A-Z][A-Z0-9_]*-)+)(\d)-([A-Z0-9_]+)")
JUNOS_TAG = re.compile(rf"^(?:{TAGS})$")
JUNOS_TAG_AT_START = re.compile(HEAD + rf"({TAGS}):")
JUNOS_STATE = re.compile(r"(?:_|NBR|ADJ)(DOWN|UP)(?:_ALARM_USER)?$")
STATE_CODES = re.compile(
    r"UPDOWN|ADJCHANGE|ADJCHG|NBRSTATE|CHANGED|IF_DOWN|IF_UP|SESSION_STATUS|NBRCHANGE"
)
TEXT_STATE = [
    (re.compile(r"to established", re.I), "up"),
    (re.compile(r"from established", re.I), "down"),
    (re.compile(r"to full\b", re.I), "up"),
    (re.compile(r"from full\b", re.I), "down"),
    (re.compile(r"\b(up|down)\b", re.I), None),  # None = use the matched word
]
ADMIN_DOWN = re.compile(r"admin(?:istratively)?[- ]down|ifAdminStatus down", re.I)
BGP_ADMIN = re.compile(
    r"User reset|Admin\.? shutdown|Administrative (?:Reset|Shutdown)|Connection Collision"
    r"|\b6/[2347]\b",
    re.I,
)
READ_ONLY_CMD = re.compile(
    r"command '(?:run\s+)?(?:show|monitor|ping|traceroute|request|file|help|exit|quit)\b", re.I
)
STP_ABNORMAL = re.compile(r"ROOTCHANGE|TOPOTRAP|BLOCK_|LOOPGUARD|ROOTGUARD|BPDUGUARD")
JSRPD_ABNORMAL = re.compile(r"^JSRPD_.*FAILOVER|^JSRPD_REDUNDANCY_MODE_CHANGE$")
CHASSISD_ABNORMAL = re.compile(r"^CHASSISD_.*(?:FAIL|OFFLINE|ALARM|OVER_TEMP|TEMP)")

PEER_IP = re.compile(r"(?:neighbor|nbr|peer|from host|from|source:)\s*'?([0-9A-Fa-f:.]+)", re.I)
IPV4_PORT = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})(?::\d+)?$")
ISIS_PEER = re.compile(r"adjacency to\s+([\w.-]+)", re.I)
IFNAME = r"([A-Za-z][\w.-]*\d[\w./:-]*)"
INTERFACE = [
    re.compile(r"interface\s+" + IFNAME, re.I),
    re.compile(r"ifName\s+" + IFNAME),
    re.compile(r"realm \S+ " + IFNAME + r" area"),
    re.compile(r"\bon\s+(?:port\s+)?" + IFNAME),
    re.compile(r"\((?!L\d\))([A-Za-z][A-Za-z-]*\d[\d/.:]*)\)"),  # "(Gi0/2)", not "(L2)"
]

COLD_START = "1.3.6.1.6.3.1.1.5.1"
LINK_DOWN, LINK_UP = "1.3.6.1.6.3.1.1.5.3", "1.3.6.1.6.3.1.1.5.4"
BGP_UP = {"1.3.6.1.2.1.15.0.1", "1.3.6.1.2.1.15.7.1", "1.3.6.1.4.1.9.9.187.0.1"}
BGP_DOWN = {"1.3.6.1.2.1.15.0.2", "1.3.6.1.2.1.15.7.2", "1.3.6.1.4.1.9.9.187.0.2"}
IF_INDEX, IF_DESCR, IF_ADMIN = (
    "1.3.6.1.2.1.2.2.1.1.",
    "1.3.6.1.2.1.2.2.1.2.",
    "1.3.6.1.2.1.2.2.1.7.",
)
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1."
# bgpPeerTable row suffix, or CISCO-BGP4-MIB cbgpPeer2Table ipv4 index (type 1, length 4)
BGP_PEER_OID = re.compile(
    r"^1\.3\.6\.1\.(?:2\.1\.15\.3\.1\.\d+|4\.1\.9\.9\.187\.1\.2\.5\.1\.\d+\.1\.4)"
    r"\.(\d+\.\d+\.\d+\.\d+)$"
)
SNMP_TYPE_PREFIX = re.compile(r"^[A-Za-z][\w-]*:\s*")


def parse_line(line: str) -> NetEvent | None:
    if not line or not line.strip():
        return None
    try:
        obj = json.loads(line)
    except (ValueError, RecursionError):
        return None
    return parse_event(obj) if isinstance(obj, dict) else None


def parse_event(obj: dict) -> NetEvent | None:
    device, ts = _ip(obj.get("source_ip")), _ts(obj.get("received_at"))
    if device is None or ts is None:
        return None
    kind = obj.get("kind")
    if kind == "syslog":
        fields = _syslog(obj)
    elif kind == "trap":
        fields = _trap(obj)
    else:
        return None
    if fields is None:
        return None
    key = "\x1f".join((kind, device, str(obj.get("received_at")), fields["raw"]))
    return NetEvent(
        id=hashlib.blake2b(key.encode(), digest_size=6).hexdigest(),
        device=device,
        ts=ts,
        **fields,
    )


def _ip(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(ipaddress.ip_address(value.strip()))
    except ValueError:
        return None


def _ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
        return ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts.astimezone(UTC)
    except (ValueError, OverflowError):
        return None


def _syslog(obj: dict) -> dict | None:
    raw = obj.get("raw")
    header = obj.get("syslog") if isinstance(obj.get("syslog"), dict) else {}
    message = header.get("message") if isinstance(header.get("message"), str) else None
    if not isinstance(raw, str):
        raw = message
    if not raw:
        return None
    text = message or raw

    code, cisco_sev = None, None
    for field in ("msgid", "appname"):
        if isinstance(header.get(field), str) and JUNOS_TAG.match(header[field]):
            code = header[field]
            break
    else:
        cisco, junos = CISCO_CODE.match(text), JUNOS_TAG_AT_START.match(text)
        # both can match when one code is quoted inside the other's text: the first one wins
        if cisco and not (junos and junos.start(1) < cisco.start(1)):
            code, cisco_sev = f"{cisco[1]}{cisco[2]}-{cisco[3]}", int(cisco[2])
        elif junos:
            code = junos[1]
    etype = next((t for pat, t in CODE_TYPES if code and re.search(pat, code)), "other")
    if code == "UI_CMDLINE_READ_LINE" and READ_ONLY_CMD.search(text):
        etype = "other"

    if cisco_sev is not None:
        severity = SEVERITIES[cisco_sev]
    elif header.get("severity") in SEVERITIES:
        severity = header["severity"]
    else:
        severity = "info"

    state = _state(code, text) if code and etype in STATEFUL else None
    hostname = header.get("hostname")
    return {
        "type": etype,
        "state": state,
        "hostname": hostname if isinstance(hostname, str) and hostname else None,
        "interface": None if etype in NO_INTERFACE else _interface(text),
        "peer": _peer(etype, text),
        "severity": severity,
        "code": code,
        "raw": raw,
        "abnormal": _abnormal(etype, state, code or "", cisco_sev, severity, text),
    }


def _abnormal(
    etype: str, state: str | None, code: str, cisco_sev: int | None, severity: str, text: str
) -> bool:
    if etype in STATEFUL:
        if state != "down":
            return False
        if etype == "link":
            return not (ADMIN_DOWN.search(text) or "ADMIN_DOWN" in code)
        return not (etype == "bgp" and BGP_ADMIN.search(text))
    if etype == "stp_change":
        return bool(STP_ABNORMAL.search(code))
    if etype == "cluster_failover":
        if cisco_sev is None:
            return bool(JSRPD_ABNORMAL.search(code))
        return bool(re.search(r"SWITCHOVER|FAILOVER", code)) or cisco_sev <= 3
    if etype == "hw_env":
        if cisco_sev is None:  # ponytail: CHASSISD allowlist + err-or-worse header, tune in lab
            return bool(CHASSISD_ABNORMAL.search(code)) or SEVERITIES.index(severity) <= 3
        return cisco_sev <= 4
    return False


def _state(code: str, text: str) -> str | None:
    if "-" not in code and (m := JUNOS_STATE.search(code)):
        return m[1].lower()
    if code.endswith("-NOTIFICATION"):
        return "down"
    if m := re.search(r"-IF_(DOWN|UP)", code):
        return m[1].lower()
    if not STATE_CODES.search(code):
        return None
    for pattern, state in TEXT_STATE:
        if m := pattern.search(text):
            return state or m[1].lower()
    return None


def _interface(text: str) -> str | None:
    for pattern in INTERFACE:
        if m := pattern.search(text):
            return m[1].rstrip(".:-")
    return None


def _peer(etype: str, text: str) -> str | None:
    if etype not in {"bgp", "ospf", "isis", "vpn", "login_failed"}:
        return None
    for m in PEER_IP.finditer(text):
        candidate = m[1].split("+")[0]
        if v4 := IPV4_PORT.match(candidate):
            candidate = v4[1]
        if ip := _ip(candidate):
            return ip
    if etype == "isis" and (m := ISIS_PEER.search(text)):
        return m[1]
    return None


def _trap(obj: dict) -> dict | None:
    trap_oid, raw_varbinds = obj.get("trap_oid"), obj.get("varbinds") or []
    if not isinstance(trap_oid, str) or not trap_oid or not isinstance(raw_varbinds, list):
        return None
    oid = trap_oid.lstrip(".")
    varbinds = {}
    for vb in raw_varbinds:
        if not isinstance(vb, dict) or not isinstance(vb.get("oid"), str):
            continue
        value = vb.get("value")
        if value is None or str(value).startswith("Hex-STRING:"):
            continue
        varbinds[vb["oid"].lstrip(".")] = _value(value)

    etype, state, interface, peer, abnormal = "other", None, None, None, False
    if oid in (LINK_DOWN, LINK_UP):
        etype, state = "link", "down" if oid == LINK_DOWN else "up"
        interface = _varbind(varbinds, IF_NAME) or _varbind(varbinds, IF_DESCR)
        if interface is None and (idx := _varbind(varbinds, IF_INDEX)):
            interface = f"ifIndex {idx}"
        admin_status = _varbind(varbinds, IF_ADMIN) or ""
        abnormal = state == "down" and not admin_status.startswith(("down", "2"))
    elif oid in BGP_UP or oid in BGP_DOWN:
        etype, state = "bgp", "up" if oid in BGP_UP else "down"
        peer = next((m[1] for k in varbinds if (m := BGP_PEER_OID.match(k))), None)
        abnormal = state == "down"
    elif oid == COLD_START:
        etype, abnormal = "hw_env", True  # the device rebooted

    severity = "warning" if abnormal else {"down": "warning", "up": "notice"}.get(state, "info")
    summary = "; ".join(f".{k} = {v}" for k, v in varbinds.items())
    return {
        "type": etype,
        "state": state,
        "hostname": None,
        "interface": interface,
        "peer": peer,
        "severity": severity,
        "code": trap_oid,
        "raw": f"trap {trap_oid}: {summary}" if summary else f"trap {trap_oid}",
        "abnormal": abnormal,
    }


def _value(value: object) -> str:
    """net-snmp prints values like 'STRING: "Gi1/0/24"' or 'INTEGER: down(2)'; keep the payload."""
    return SNMP_TYPE_PREFIX.sub("", str(value)).strip().strip('"')


def _varbind(varbinds: dict[str, str], prefix: str) -> str | None:
    return next((v for k, v in varbinds.items() if k.startswith(prefix) and v), None)
