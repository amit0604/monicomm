import json
from datetime import UTC

import pytest

from app.modules.investigator.events import EVENT_TYPES, parse_event, parse_line

TS = "2026-11-25T10:00:00.123Z"


def syslog(message, severity="notice", hostname="r1", source_ip="10.255.0.1", **header):
    raw = f"<189>Nov 25 10:00:00 {hostname} {message}"
    return json.dumps(
        {
            "schema": "monicomm.syslog.v1",
            "kind": "syslog",
            "collector_id": "moni-syslog-01",
            "source_ip": source_ip,
            "received_at": TS,
            "raw": raw,
            "syslog": {"severity": severity, "hostname": hostname, "message": message, **header},
        }
    )


def trap(trap_oid, varbinds, source_ip="10.255.0.9"):
    return json.dumps(
        {
            "schema": "monicomm.trap.v1",
            "kind": "trap",
            "collector_id": "moni-snmp-01",
            "source_ip": source_ip,
            "received_at": TS,
            "trap_oid": trap_oid,
            "device_uptime": "(123456) 0:20:34.56",
            "varbinds": [{"oid": o, "value": v} for o, v in varbinds],
        }
    )


# (line, type, state, interface, peer, abnormal)
CASES = [
    # link
    (
        syslog("%LINK-3-UPDOWN: Interface GigabitEthernet1/0/24, changed state to down", "err"),
        "link",
        "down",
        "GigabitEthernet1/0/24",
        None,
        True,
    ),
    (
        syslog(
            "%LINEPROTO-5-UPDOWN: Line protocol on Interface GigabitEthernet1/0/24, "
            "changed state to up"
        ),
        "link",
        "up",
        "GigabitEthernet1/0/24",
        None,
        False,
    ),
    (
        syslog(
            "RP/0/RSP0/CPU0:Nov 25 10:00:00: ifmgr[215]: %PKT_INFRA-LINK-3-UPDOWN : "
            "Interface GigabitEthernet0/0/0/0, changed state to Down",
            "err",
        ),
        "link",
        "down",
        "GigabitEthernet0/0/0/0",
        None,
        True,
    ),
    (
        syslog(
            "SNMP_TRAP_LINK_DOWN: ifIndex 529, ifAdminStatus up(1), ifOperStatus down(2), "
            "ifName ge-0/0/1",
            "warning",
            appname="mib2d",
        ),
        "link",
        "down",
        "ge-0/0/1",
        None,
        True,
    ),
    (
        syslog(
            "SNMP_TRAP_LINK_UP: ifIndex 529, ifAdminStatus up(1), ifOperStatus up(1), "
            "ifName ge-0/0/1",
            "info",
            appname="mib2d",
        ),
        "link",
        "up",
        "ge-0/0/1",
        None,
        False,
    ),
    # config
    (
        syslog("%SYS-5-CONFIG_I: Configured from console by admin on vty0 (10.1.1.50)"),
        "config_change",
        None,
        None,
        None,
        False,
    ),
    (
        syslog("%PARSER-5-CFGLOG_LOGGEDCMD: User:admin  logged command:interface Gi1/0/1"),
        "config_change",
        None,
        None,
        None,
        False,
    ),
    (
        syslog(
            "UI_COMMIT: User 'admin' requested 'commit' operation (comment: none)", appname="mgd"
        ),
        "config_change",
        None,
        None,
        None,
        False,
    ),
    # login
    (
        syslog(
            "%SEC_LOGIN-4-LOGIN_FAILED: Login failed [user: admin] [Source: 10.1.1.50] "
            "[localport: 22] [Reason: Login Authentication Failed]",
            "warning",
        ),
        "login_failed",
        None,
        None,
        "10.1.1.50",
        False,
    ),
    (
        syslog(
            "SSHD_LOGIN_FAILED: Login failed for user 'root' from host '10.1.1.51'",
            "warning",
            appname="sshd",
        ),
        "login_failed",
        None,
        None,
        "10.1.1.51",
        False,
    ),
    # bgp
    (
        syslog("%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down BGP Notification sent"),
        "bgp",
        "down",
        None,
        "10.0.0.2",
        True,
    ),
    (
        syslog("%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Up"),
        "bgp",
        "up",
        None,
        "10.0.0.2",
        False,
    ),
    (
        syslog(
            "%BGP-3-NOTIFICATION: sent to neighbor 10.0.0.2 4/0 (hold time expired) 0 bytes", "err"
        ),
        "bgp",
        "down",
        None,
        "10.0.0.2",
        True,
    ),
    (
        syslog(
            "RPD_BGP_NEIGHBOR_STATE_CHANGED: BGP peer 10.0.0.6+179 (External AS 65002) "
            "changed state from Established to Idle (event HoldTime)",
            appname="rpd",
        ),
        "bgp",
        "down",
        None,
        "10.0.0.6",
        True,
    ),
    (
        syslog(
            "RPD_BGP_NEIGHBOR_STATE_CHANGED: BGP peer 10.0.0.6 (External AS 65002) "
            "changed state from OpenConfirm to Established (event RecvKeepAlive)",
            appname="rpd",
        ),
        "bgp",
        "up",
        None,
        "10.0.0.6",
        False,
    ),
    # ospf
    (
        syslog(
            "%OSPF-5-ADJCHG: Process 1, Nbr 10.0.0.2 on GigabitEthernet0/1 from FULL to "
            "DOWN, Neighbor Down: Dead timer expired"
        ),
        "ospf",
        "down",
        "GigabitEthernet0/1",
        "10.0.0.2",
        True,
    ),
    (
        syslog(
            "%OSPF-5-ADJCHG: Process 1, Nbr 10.0.0.2 on GigabitEthernet0/1 from LOADING to "
            "FULL, Loading Done"
        ),
        "ospf",
        "up",
        "GigabitEthernet0/1",
        "10.0.0.2",
        False,
    ),
    (
        syslog(
            "RPD_OSPF_NBRDOWN: OSPF neighbor 10.0.0.5 (realm ospf-v2 ge-0/0/1.0 area 0.0.0.0) "
            "state changed from Full to Down due to KillNbr",
            appname="rpd",
        ),
        "ospf",
        "down",
        "ge-0/0/1.0",
        "10.0.0.5",
        True,
    ),
    (
        syslog(
            "RPD_OSPF_NBRUP: OSPF neighbor 10.0.0.5 (realm ospf-v2 ge-0/0/1.0 area 0.0.0.0) "
            "state changed from Loading to Full due to LoadDone",
            appname="rpd",
        ),
        "ospf",
        "up",
        "ge-0/0/1.0",
        "10.0.0.5",
        False,
    ),
    # isis
    (
        syslog(
            "%CLNS-5-ADJCHANGE: ISIS: Adjacency to R2 (GigabitEthernet0/2) Down, hold time "
            "expired"
        ),
        "isis",
        "down",
        "GigabitEthernet0/2",
        "R2",
        True,
    ),
    (
        syslog(
            "RPD_ISIS_ADJDOWN: IS-IS lost L2 adjacency to R3 on ge-0/0/2.0, reason: Aged Out",
            appname="rpd",
        ),
        "isis",
        "down",
        "ge-0/0/2.0",
        "R3",
        True,
    ),
    (
        syslog("RPD_ISIS_ADJUP: IS-IS new L2 adjacency to R3 on ge-0/0/2.0", appname="rpd"),
        "isis",
        "up",
        "ge-0/0/2.0",
        "R3",
        False,
    ),
    # vpn
    (
        syslog(
            "%CRYPTO-5-SESSION_STATUS: Crypto tunnel is DOWN. Peer 203.0.113.2:500 "
            "Id: 203.0.113.2"
        ),
        "vpn",
        "down",
        None,
        "203.0.113.2",
        True,
    ),
    (
        syslog("KMD_VPN_DOWN_ALARM_USER: VPN to-site2 from 203.0.113.7 is down.", appname="kmd"),
        "vpn",
        "down",
        None,
        "203.0.113.7",
        True,
    ),
    (
        syslog("KMD_VPN_UP_ALARM_USER: VPN to-site2 from 203.0.113.7 is up.", appname="kmd"),
        "vpn",
        "up",
        None,
        "203.0.113.7",
        False,
    ),
    # cluster, stp, hw
    (
        syslog("%REDUNDANCY-3-SWITCHOVER: RP switchover (PEER_DOWN_INTERRUPT)", "err"),
        "cluster_failover",
        None,
        None,
        None,
        True,
    ),
    (
        syslog(
            "JSRPD_REDUNDANCY_MODE_CHANGE: Redundancy mode for redundancy group 1 changed "
            "from secondary to primary",
            appname="jsrpd",
        ),
        "cluster_failover",
        None,
        None,
        None,
        True,
    ),
    (
        syslog(
            "%SPANTREE-2-BLOCK_BPDUGUARD: Received BPDU on port Gi1/0/5 with BPDU Guard "
            "enabled. Disabling port.",
            "crit",
        ),
        "stp_change",
        None,
        "Gi1/0/5",
        None,
        True,
    ),
    (
        syslog("%ENVMON-3-FAN_FAILED: Fan 2 not rotating", "err"),
        "hw_env",
        None,
        None,
        None,
        True,
    ),
    (
        syslog("CHASSISD_FRU_OFFLINE_NOTICE: Taking FPC 0 PIC 1 offline", appname="chassisd"),
        "hw_env",
        None,
        None,
        None,
        True,
    ),
    # other
    (
        syslog("%SYS-6-LOGGINGHOST_STARTSTOP: Logging to host 10.9.9.9 started", "info"),
        "other",
        None,
        None,
        None,
        False,
    ),
    (syslog("just some text", "info"), "other", None, None, None, False),
    # traps
    (
        trap(
            ".1.3.6.1.6.3.1.1.5.3",
            [
                (".1.3.6.1.2.1.2.2.1.1.24", "INTEGER: 24"),
                (".1.3.6.1.2.1.2.2.1.7.24", "INTEGER: up(1)"),
                (".1.3.6.1.2.1.31.1.1.1.1.24", 'STRING: "Gi1/0/24"'),
            ],
        ),
        "link",
        "down",
        "Gi1/0/24",
        None,
        True,
    ),
    (
        trap(
            ".1.3.6.1.6.3.1.1.5.4",
            [
                (".1.3.6.1.2.1.2.2.1.1.24", "24"),
                (".1.3.6.1.2.1.2.2.1.2.24", '"GigabitEthernet1/0/24"'),
            ],
        ),
        "link",
        "up",
        "GigabitEthernet1/0/24",
        None,
        False,
    ),
    (
        trap(".1.3.6.1.6.3.1.1.5.3", [(".1.3.6.1.2.1.2.2.1.1.7", "INTEGER: 7")]),
        "link",
        "down",
        "ifIndex 7",
        None,
        True,
    ),
    (
        trap(
            ".1.3.6.1.2.1.15.0.2",
            [
                (".1.3.6.1.2.1.15.3.1.14.10.0.0.2", "Hex-STRING: 04 00"),
                (".1.3.6.1.2.1.15.3.1.2.10.0.0.2", "INTEGER: idle(1)"),
            ],
        ),
        "bgp",
        "down",
        None,
        "10.0.0.2",
        True,
    ),
    (
        trap(".1.3.6.1.2.1.15.7.1", [(".1.3.6.1.2.1.15.3.1.2.10.0.0.3", "6")]),
        "bgp",
        "up",
        None,
        "10.0.0.3",
        False,
    ),
    (
        trap(".1.3.6.1.4.1.9.9.41.2.0.1", [(".1.3.6.1.4.1.9.9.41.1.2.3.1.2.1", "SYS")]),
        "other",
        None,
        None,
        None,
        False,
    ),
]


@pytest.mark.parametrize(("line", "etype", "state", "interface", "peer", "abnormal"), CASES)
def test_mapping(line, etype, state, interface, peer, abnormal):
    ev = parse_line(line)
    assert ev is not None
    obj = json.loads(line)
    assert ev.type in EVENT_TYPES
    assert (ev.type, ev.state, ev.interface, ev.peer, ev.abnormal) == (
        etype,
        state,
        interface,
        peer,
        abnormal,
    )
    assert ev.device == obj["source_ip"]


def test_syslog_fields():
    ev = parse_line(syslog("%LINK-3-UPDOWN: Interface Gi1/0/1, changed state to down", "err"))
    assert ev.code == "LINK-3-UPDOWN"
    assert ev.severity == "err"
    assert ev.hostname == "r1"
    assert ev.raw.startswith("<189>")
    assert ev.ts.tzinfo is not None
    assert ev.ts.utcoffset().total_seconds() == 0
    assert ev.ts.tzinfo == UTC
    assert (ev.ts.hour, ev.ts.microsecond) == (10, 123000)


def test_trap_fields():
    ev = parse_line(trap(".1.3.6.1.6.3.1.1.5.3", [(".1.3.6.1.2.1.2.2.1.1.3", "3")]))
    assert ev.code == ".1.3.6.1.6.3.1.1.5.3"
    assert ev.severity == "warning"
    assert ev.hostname is None
    assert ".1.3.6.1.2.1.2.2.1.1.3 = 3" in ev.raw
    up = parse_line(trap(".1.3.6.1.6.3.1.1.5.4", []))
    assert up.severity == "notice"
    assert up.interface is None


def test_admin_down_is_not_abnormal():
    ev = parse_line(
        syslog("%LINK-5-CHANGED: Interface Gi1/0/3, changed state to " "administratively down")
    )
    assert (ev.type, ev.state, ev.interface, ev.abnormal) == ("link", "down", "Gi1/0/3", False)
    junos = parse_line(
        syslog(
            "SNMP_TRAP_LINK_DOWN: ifIndex 530, ifAdminStatus down(2), "
            "ifOperStatus down(2), ifName ge-0/0/2"
        )
    )
    assert (junos.state, junos.abnormal) == ("down", False)
    tr = parse_line(trap(".1.3.6.1.6.3.1.1.5.3", [(".1.3.6.1.2.1.2.2.1.7.9", "INTEGER: down(2)")]))
    assert (tr.state, tr.abnormal) == ("down", False)


def test_missing_syslog_header_falls_back_to_raw():
    line = json.dumps(
        {
            "kind": "syslog",
            "source_ip": "10.255.0.2",
            "received_at": TS,
            "raw": "<189>Nov 25 r1 %OSPF-5-ADJCHG: Nbr 10.0.0.9 on Gi0/3 from FULL to DOWN",
            "parse_error": "unable to parse input as valid syslog message",
        }
    )
    ev = parse_line(line)
    assert (ev.type, ev.state, ev.peer, ev.interface) == ("ospf", "down", "10.0.0.9", "Gi0/3")
    assert ev.severity == "notice"  # from the Cisco severity digit
    assert ev.hostname is None


def test_syslog_without_raw_or_header_message_is_skipped():
    assert parse_event({"kind": "syslog", "source_ip": "10.0.0.1", "received_at": TS}) is None


@pytest.mark.parametrize(
    "line",
    [
        "",
        "   \n",
        "{not json",
        "[1, 2]",
        json.dumps(
            {
                "kind": "snmp_metric",
                "source_ip": "10.0.0.1",
                "received_at": TS,
                "measurement": "snmp_interface",
                "tags": {},
                "fields": {},
                "polled_at": 1,
            }
        ),
        json.dumps({"name": "component_received_events_total", "collector_id": "moni-syslog-01"}),
        json.dumps({"kind": "syslog", "received_at": TS, "raw": "x"}),
        json.dumps({"kind": "syslog", "source_ip": "10.0.0.1", "raw": "x"}),
        json.dumps(
            {"kind": "syslog", "source_ip": "10.0.0.1", "received_at": "yesterday", "raw": "x"}
        ),
        json.dumps({"kind": "trap", "source_ip": "10.0.0.1", "received_at": TS}),
    ],
)
def test_skipped_lines(line):
    assert parse_line(line) is None


def test_naive_timestamp_is_treated_as_utc():
    ev = parse_event(
        {
            "kind": "syslog",
            "source_ip": "10.0.0.1",
            "received_at": "2026-11-25T10:00:00",
            "raw": "x",
        }
    )
    assert ev.ts.tzinfo == UTC


def test_id_is_stable_and_distinct():
    a = syslog("%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down")
    b = syslog("%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Up")
    assert parse_line(a).id == parse_line(a).id
    assert parse_line(a).id != parse_line(b).id
    assert (
        parse_line(a).id
        != parse_line(syslog("%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down", source_ip="10.255.0.3")).id
    )
    assert len(parse_line(a).id) == 12


def test_bgp_transition_without_established_has_no_state():
    ev = parse_line(
        syslog(
            "RPD_BGP_NEIGHBOR_STATE_CHANGED: BGP peer 10.0.0.6 (External AS 65002) "
            "changed state from OpenConfirm to Active (event RecvNotify)"
        )
    )
    assert (ev.type, ev.state, ev.peer, ev.abnormal) == ("bgp", None, "10.0.0.6", False)


def test_routine_hw_message_is_not_abnormal():
    line = json.dumps(
        {
            "schema": "monicomm.syslog.v1",
            "kind": "syslog",
            "source_ip": "10.0.0.1",
            "received_at": "2026-11-25T10:00:00Z",
            "raw": "%PLATFORM-6-FAN_OK: Fan tray 1 is OK",
            "syslog": {"severity": "info", "message": "%PLATFORM-6-FAN_OK: Fan tray 1 is OK"},
        }
    )
    ev = parse_line(line)
    assert ev.type == "hw_env"
    assert ev.abnormal is False


def test_cisco_eem_is_not_cluster_failover():
    line = json.dumps(
        {
            "kind": "syslog",
            "source_ip": "10.0.0.1",
            "received_at": "2026-11-25T10:00:00Z",
            "raw": "%HA_EM-6-LOG: backup_script: done",
        }
    )
    ev = parse_line(line)
    assert ev.type == "other"
    assert ev.abnormal is False


def bare(raw, source_ip="10.0.0.1", received_at=TS, **extra):
    """A syslog line whose header could not be parsed (raw only)."""
    return json.dumps(
        {"kind": "syslog", "source_ip": source_ip, "received_at": received_at, "raw": raw, **extra}
    )


# 1. log injection: user-controlled text later in the line must not pick the event type
@pytest.mark.parametrize(
    ("line", "etype"),
    [
        (
            syslog(
                "SSHD_LOGIN_FAILED: Login failed for user '%REDUNDANCY-1-SWITCHOVER' "
                "from host '10.1.1.51'",
                appname="sshd",
            ),
            "login_failed",
        ),
        (
            syslog(
                "SSHD_LOGIN_FAILED: Login failed for user 'x' from host '10.1.1.51'",
                appname="sshd",
                msgid="SSHD_LOGIN_FAILED",
            ),
            "login_failed",
        ),
        (
            syslog(
                "%SEC_LOGIN-4-LOGIN_FAILED: Login failed [user: %LINK-3-UPDOWN] "
                "[Source: 10.1.1.50]"
            ),
            "login_failed",
        ),
        (
            syslog("%SYS-5-CONFIG_I: Configured from console by RPD_OSPF_NBRDOWN: on vty0"),
            "config_change",
        ),
        (syslog("sshd[77]: Failed password for user JSRPD_X from 10.1.1.9"), "other"),
        (syslog("description core uplink %ENVMON-1-SHUTDOWN: fake", "info") + "", "other"),
        (bare("x" * 120 + " %REDUNDANCY-1-SWITCHOVER: fake"), "other"),
    ],
)
def test_injected_codes_are_ignored(line, etype):
    ev = parse_line(line)
    assert ev.type == etype
    assert ev.abnormal is False


def test_junos_tag_from_msgid_and_after_proc_prefix():
    ev = parse_line(
        syslog(
            "ifIndex 529, ifAdminStatus up(1), ifOperStatus down(2), ifName ge-0/0/1",
            msgid="SNMP_TRAP_LINK_DOWN",
        )
    )
    assert (ev.type, ev.state, ev.abnormal, ev.code) == (
        "link",
        "down",
        True,
        "SNMP_TRAP_LINK_DOWN",
    )
    raw = bare("<28>Nov 25 10:00:00 mx1 mib2d[1234]: SNMP_TRAP_LINK_DOWN: ifName ge-0/0/1, x")
    ev = parse_line(raw)
    assert (ev.type, ev.state, ev.interface) == ("link", "down", "ge-0/0/1")


# 2. crashes return None
@pytest.mark.parametrize(
    "line",
    [
        bare("x", received_at="0001-01-01T00:00:00+05:00"),
        bare("x", received_at="9999-12-31T23:59:59-05:00"),
        json.dumps(
            {
                "kind": "trap",
                "source_ip": "10.0.0.1",
                "received_at": TS,
                "trap_oid": ".1.3.6.1.6.3.1.1.5.3",
                "varbinds": "oops",
            }
        ),
        bare("x", source_ip="not-an-ip"),
        bare("x", source_ip="   "),
        bare("x", source_ip=12),
    ],
)
def test_bad_input_returns_none(line):
    assert parse_line(line) is None


def test_non_str_hostname_and_padded_source_ip():
    line = json.dumps(
        {
            "kind": "syslog",
            "source_ip": " 10.0.0.1 ",
            "received_at": TS,
            "raw": "x",
            "syslog": {"hostname": ["r1"], "message": "x", "msgid": 5, "severity": ["err"]},
        }
    )
    ev = parse_line(line)
    assert (ev.hostname, ev.device, ev.severity) == (None, "10.0.0.1", "info")


# 3. IOS-XR admin-down
def test_xr_admin_down_is_not_abnormal():
    ev = parse_line(
        syslog(
            "%PKT_INFRA-LINK-3-UPDOWN : Interface GigabitEthernet0/0/0/1, "
            "changed state to Admin-Down"
        )
    )
    assert (ev.type, ev.state, ev.abnormal) == ("link", "down", False)


# 4. BGP admin and benign resets
@pytest.mark.parametrize(
    "message",
    [
        "%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down User reset",
        "%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down Admin. shutdown",
        "%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down Admin. Shutdown",
        "%BGP-5-ADJCHANGE: neighbor 10.0.0.2 Down Connection Collision",
        "%BGP-3-NOTIFICATION: sent to neighbor 10.0.0.2 6/4 (Administrative Reset) 0 bytes",
        "%BGP-3-NOTIFICATION: received from neighbor 10.0.0.2 6/2 (Administrative Shutdown)",
    ],
)
def test_bgp_admin_reset_is_not_abnormal(message):
    ev = parse_line(syslog(message))
    assert (ev.type, ev.state, ev.peer, ev.abnormal) == ("bgp", "down", "10.0.0.2", False)


def test_bgp_hold_timer_is_still_abnormal():
    ev = parse_line(syslog("%BGP-3-NOTIFICATION: sent to neighbor 10.0.0.2 4/0 (hold time)"))
    assert ev.abnormal is True


# 5. gates on always-abnormal types
@pytest.mark.parametrize(
    "message",
    [
        "%SPANTREE-5-EXTENDED_SYSID: Extended SysId enabled for type vlan",
        "%SPANTREE-6-PORT_STATE: Port Gi1/0/1 instance 10 moving from learning to forwarding",
        "%REDUNDANCY-6-STANDBY_READY: The standby RP is ready",
        "JSRPD_HA_HEALTH_WEIGHT_RECOVERY: Redundancy group 1 health weight recovered",
        "%PLATFORM-5-SIGNATURE_VERIFIED: Image 'bootflash:x.bin' passed code signing",
        "%ENVMON-5-FAN_OK: Fan 2 is OK",
        "CHASSISD_SNMP_TRAP7: SNMP trap generated: FRU power on",
        "%REDUNDANCY-5-PEER_MONITOR_EVENT: Active detected a standby insertion",
    ],
)
def test_routine_events_are_not_abnormal(message):
    ev = parse_line(syslog(message, "warning"))
    assert ev.type in ("stp_change", "cluster_failover", "hw_env")
    assert ev.abnormal is False


@pytest.mark.parametrize(
    "message",
    [
        "%ENVMON-3-FAN_FAILED: Fan 2 not rotating",
        "%SPANTREE-5-TOPOTRAP: Topology Change Trap for vlan 10",
        "%SPANTREE-5-ROOTCHANGE: Root Changed for vlan 10",
        "%REDUNDANCY-5-SWITCHOVER: RP switchover (manual)",
        "%REDUNDANCY-3-PEER_DOWN: peer RP went down",
        "%PLATFORM_ENV-1-FAN: Faulty fan detected",
        "JSRPD_SET_FAILOVER: Redundancy group 1 failover",
        "CHASSISD_OVER_TEMP_CONDITION: FPC 0 over temperature",
    ],
)
def test_real_failures_are_abnormal(message):
    ev = parse_line(syslog(message, "info"))
    assert ev.abnormal is True


def test_cisco_severity_digit_wins_over_header():
    ev = parse_line(syslog("%ENVMON-3-FAN_FAILED: Fan 2 not rotating", "info"))
    assert (ev.severity, ev.abnormal) == ("err", True)


def test_junos_hw_uses_header_severity_when_not_allowlisted():
    assert parse_line(syslog("CHASSISD_RE_WARM_BOOT: reboot", "crit")).abnormal is True
    assert parse_line(syslog("CHASSISD_RE_WARM_BOOT: reboot", "notice")).abnormal is False


# 6. interface needs a digit
@pytest.mark.parametrize(
    "message",
    [
        "%LINK-3-UPDOWN: Interface down detected, changed state to down",
        "%ROUTING-ISIS-5-ADJCHANGE : Adjacency to R2 (L2) Down, Interface state down",
        "%LINEPROTO-5-UPDOWN: Interface flap detected, changed state to up",
    ],
)
def test_interface_words_are_not_interfaces(message):
    assert parse_line(syslog(message)).interface is None


# 7. peers are validated and never set for links
def test_peer_validation():
    link = parse_line(syslog("%LINK-3-UPDOWN: Interface Gi1/0/1 from 10.0.0.2, state to down"))
    assert link.peer is None
    bad = parse_line(syslog("%BGP-5-ADJCHANGE: neighbor 999.1.1.1 Down"))
    assert (bad.peer, bad.abnormal) == (None, True)
    v6 = parse_line(syslog("%BGP-5-ADJCHANGE: neighbor 2001:db8::2 Down"))
    assert v6.peer == "2001:db8::2"
    login = parse_line(syslog("SSHD_LOGIN_FAILED: Login failed for user 'a' from host 'bad'"))
    assert login.peer is None


# 8. text-state fallback only for state-carrying codes
def test_crypto_without_state_code_has_no_state():
    ev = parse_line(syslog("%CRYPTO-4-RECVD_PKT_INV_SPI: decaps: rec'd IPSEC packet is down x"))
    assert (ev.type, ev.state, ev.abnormal) == ("vpn", None, False)


def test_eigrp_neighbor_change_stays_other():
    ev = parse_line(syslog("%DUAL-5-NBRCHANGE: EIGRP-IPv4 1: Neighbor 10.0.0.2 (Gi0/1) is down"))
    assert (ev.type, ev.abnormal) == ("other", False)


# 9. read-only Junos CLI commands are not config changes
@pytest.mark.parametrize(
    ("command", "etype"),
    [
        ("show interfaces terse", "other"),
        ("run ping 10.0.0.1", "other"),
        ("monitor traffic", "other"),
        ("set interfaces ge-0/0/1 disable", "config_change"),
    ],
)
def test_cmdline_read_line(command, etype):
    msg = f"UI_CMDLINE_READ_LINE: User 'admin', command '{command} '"
    assert parse_line(syslog(msg, appname="mgd")).type == etype


# 10. new mappings
@pytest.mark.parametrize(
    ("message", "etype", "state", "interface", "abnormal"),
    [
        (
            "%ETHPORT-5-IF_DOWN_LINK_FAILURE: Interface Ethernet1/1 is down (Link failure)",
            "link",
            "down",
            "Ethernet1/1",
            True,
        ),
        (
            "%ETHPORT-5-IF_DOWN_ADMIN_DOWN: Interface Ethernet1/2 is down (Administratively down)",
            "link",
            "down",
            "Ethernet1/2",
            False,
        ),
        (
            "%ETHPORT-5-IF_UP: Interface Ethernet1/1 is up in mode access",
            "link",
            "up",
            "Ethernet1/1",
            False,
        ),
        (
            "%OSPF-5-NBRSTATE: ospf-1 [1234] Nbr 10.0.0.2 on Ethernet1/1 went from FULL to DOWN",
            "ospf",
            "down",
            "Ethernet1/1",
            True,
        ),
        (
            "%OSPFV3-5-ADJCHG: Process 1, Nbr 10.0.0.2 on Gi0/1 from LOADING to FULL",
            "ospf",
            "up",
            "Gi0/1",
            False,
        ),
    ],
)
def test_new_syslog_mappings(message, etype, state, interface, abnormal):
    ev = parse_line(syslog(message))
    assert (ev.type, ev.state, ev.interface, ev.abnormal) == (etype, state, interface, abnormal)


def test_cold_start_and_cisco_bgp_traps():
    cold = parse_line(trap(".1.3.6.1.6.3.1.1.5.1", []))
    assert (cold.type, cold.abnormal, cold.severity) == ("hw_env", True, "warning")
    down = parse_line(
        trap(".1.3.6.1.4.1.9.9.187.0.2", [(".1.3.6.1.4.1.9.9.187.1.2.5.1.3.1.4.10.0.0.8", "1")])
    )
    assert (down.type, down.state, down.peer, down.abnormal) == ("bgp", "down", "10.0.0.8", True)
    up = parse_line(trap(".1.3.6.1.4.1.9.9.187.0.1", []))
    assert (up.type, up.state, up.abnormal) == ("bgp", "up", False)


# 11. trap values
def test_trap_skips_none_and_hex_values():
    ev = parse_line(
        trap(
            ".1.3.6.1.6.3.1.1.5.3",
            [
                (".1.3.6.1.2.1.31.1.1.1.1.5", "Hex-STRING: 47 69 31"),
                (".1.3.6.1.2.1.2.2.1.2.5", None),
                (".1.3.6.1.2.1.2.2.1.1.5", "INTEGER: 5"),
                ("bad", None),
            ],
        )
    )
    assert ev.interface == "ifIndex 5"
    assert "Hex-STRING" not in ev.raw
    assert "None" not in ev.raw


def test_deeply_nested_json_returns_none():
    assert parse_line("[" * 100000 + "]" * 100000) is None
    assert parse_line('{"a": ' + "[" * 100000 + "]" * 100000 + "}") is None
