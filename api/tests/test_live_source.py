"""Live collector data (app.core.live_snmp) and how Dashboard, Mapper, Analyzer and chat use it."""

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.ai import llm_client
from app.core import live_snmp
from app.core.config import get_settings
from app.main import app
from app.modules.analyzer import service as analyzer_service
from app.modules.analyzer.demo import DemoTopology
from app.modules.analyzer.live import CombinedTopology, LiveTopology
from app.modules.dashboard.demo import DemoSource
from app.modules.dashboard.live import CombinedSource, LiveSource
from app.modules.dashboard.service import without_live
from app.modules.mapper.live import links_from

client = TestClient(app)
NOW = 1_795_627_800.0  # seconds
CISCO = "10.100.102.161"
JUNOS = "10.100.102.162"


def rec(ip, name, measurement, fields, t=NOW, index=None, **tags):
    tags = {"source": ip, "sysName": name, **tags}
    if index is not None:
        tags["index"] = index
    return json.dumps(
        {
            "schema": "monicomm.snmp_metric.v1",
            "kind": "snmp_metric",
            "collector_id": "lab-snmp",
            "source_ip": ip,
            "measurement": measurement,
            "tags": tags,
            "fields": fields,
            "polled_at": int(t * 1000),
        }
    )


def iface(ip, name, index, if_name, octets_in, octets_out, t, speed=10, oper=1, alias=""):
    return rec(
        ip,
        name,
        "snmp_interface",
        {
            "ifAdminStatus": 1,
            "ifOperStatus": oper,
            "ifHighSpeed": speed,
            "ifHCInOctets": octets_in,
            "ifHCOutOctets": octets_out,
            "ifInErrors": 0,
            "ifOutErrors": 3,
            "ifAlias": alias,
        },
        t=t,
        index=index,
        ifName=if_name,
    )


def lab_lines():
    cisco_descr = (
        "Cisco IOS Software, C2960X Software (C2960X-UNIVERSALK9-M), Version 15.2(7)E8 [lab]"
    )
    junos_descr = "Juniper Networks, Inc. ex2300-24t Ethernet Switch, kernel JUNOS 21.4R3-S5"
    return [
        rec(CISCO, "lab-cisco1", "snmp_system", {"sysUpTime": 144003}, t=NOW - 30),
        rec(
            CISCO,
            "lab-cisco1",
            "snmp_identity",
            {"sysDescr": cisco_descr, "sysObjectID": ".1.3.6.1.4.1.9.1.1208", "sysLocation": "Lab"},
        ),
        rec(
            CISCO,
            "lab-cisco1",
            "snmp_cisco_cpu",
            {"cpmCPUTotal5minRev": 12, "cpmCPUMemoryUsed": 30, "cpmCPUMemoryFree": 70},
            index="1",
        ),
        # 10 Mbps port: 750_000 bytes in 60 s = 100 kbit/s = 1 % in; out counter wrapped
        iface(CISCO, "lab-cisco1", "3", "Gi0/1", 1_000_000, 900, NOW - 60),
        iface(CISCO, "lab-cisco1", "3", "Gi0/1", 1_750_000, 100, NOW),
        iface(CISCO, "lab-cisco1", "4", "Gi0/2", 0, 0, NOW, oper=2),
        # LLDP on port 3 sees the Juniper by name; the remote port is matched by its alias
        rec(
            CISCO,
            "lab-cisco1",
            "snmp_lldp_neighbor",
            {
                "lldpRemChassisId": "aa:bb",
                "lldpRemPortId": "uplink-to-cisco",
                "lldpRemPortDesc": "",
                "lldpRemSysName": "lab-junos1.lab.local",
            },
            index="0.3.1",
        ),
        # a stale neighbor from an hour ago, and one that is never polled
        rec(
            CISCO,
            "lab-cisco1",
            "snmp_lldp_neighbor",
            {"lldpRemSysName": "gone"},
            t=NOW - 3600,
            index="0.4.9",
        ),
        rec(
            CISCO,
            "lab-cisco1",
            "snmp_lldp_neighbor",
            {"lldpRemSysName": "phone-1", "lldpRemPortId": "eth0"},
            index="0.4.2",
        ),
        # Juniper: last system poll 10 minutes ago, so it is down
        rec(JUNOS, "lab-junos1", "snmp_system", {"sysUpTime": 500}, t=NOW - 600),
        rec(
            JUNOS,
            "lab-junos1",
            "snmp_identity",
            {"sysDescr": junos_descr, "sysObjectID": ".1.3.6.1.4.1.2636.1.1.1.2.132"},
            t=NOW - 600,
        ),
        rec(
            JUNOS,
            "lab-junos1",
            "snmp_juniper_operating",
            {"jnxOperatingCPU": 7, "jnxOperatingBuffer": 40, "jnxOperatingTemp": 0},
            t=NOW - 600,
            index="9.1.0.0",
            jnxOperatingDescr="Routing Engine",
        ),
        iface(JUNOS, "lab-junos1", "5", "ge-0/0/0", 0, 0, NOW - 600, alias="uplink-to-cisco"),
        # the same link seen from the Juniper side: must not appear twice
        rec(
            JUNOS,
            "lab-junos1",
            "snmp_lldp_neighbor",
            {"lldpRemPortId": "Gi0/1", "lldpRemSysName": "lab-cisco1"},
            t=NOW - 600,
            index="0.5.1",
        ),
        "not json",
        json.dumps({"measurement": "snmp_system", "fields": {}}),  # no device, no time
    ]


@pytest.fixture
def devices():
    return {d.name: d for d in live_snmp.build(lab_lines(), now=NOW)}


def test_parses_devices_status_and_metrics(devices):
    assert sorted(devices) == ["lab-cisco1", "lab-junos1"]
    cisco, junos = devices["lab-cisco1"], devices["lab-junos1"]
    assert cisco.up and not junos.up
    assert cisco.uptime_seconds == 1440
    assert (cisco.cpu_pct, cisco.memory_pct) == (12, 30.0)
    assert (junos.cpu_pct, junos.memory_pct, junos.temperature_c) == (7, 40, None)
    port = cisco.ports[0]
    assert (port.name, port.in_util_pct, port.out_util_pct) == ("Gi0/1", 1.0, None)
    assert cisco.ports[1].oper_up is False and cisco.ports[1].in_util_pct is None
    assert [n.sys_name for n in cisco.neighbors] == ["lab-junos1.lab.local", "phone-1"]


def test_dashboard_device_fields(devices):
    source = LiveSource("unused")
    source.live_devices = lambda: list(devices.values())
    by_name = {d.name: d for d in source.devices()}
    cisco, junos = by_name["lab-cisco1"], by_name["lab-junos1"]
    assert (cisco.vendor, cisco.model, cisco.type, cisco.os_version, cisco.status) == (
        "Cisco",
        "C2960X",
        "switch",
        "IOS 15.2(7)E8",
        "online",
    )
    assert (junos.vendor, junos.model, junos.os_version, junos.status) == (
        "Juniper",
        "EX2300-24T",
        "Junos 21.4R3-S5",
        "offline",
    )
    details = source.device(f"live-{CISCO}")
    assert details.metrics.cpu_pct == 12 and details.interfaces[1].oper_status == "down"
    assert source.device("live-nope") is None
    assert [a.device_name for a in source.open_alerts()] == ["lab-junos1"]
    assert source.events() == []


def test_lldp_links_are_matched_and_deduplicated(devices):
    links = links_from(list(devices.values()))
    pairs = [(x.a.device, x.a.port, x.b.device, x.b.port) for x in links]
    assert pairs == [
        ("lab-cisco1", "Gi0/1", "lab-junos1", "ge-0/0/0"),
        ("lab-cisco1", "Gi0/2", "phone-1", "eth0"),  # not polled: left for the Mapper to count
    ]
    assert links[0].speed_mbps == 10


def test_analyzer_topology_from_live(tmp_path, devices):
    live_snmp._cache[str(tmp_path)] = (time.monotonic(), list(devices.values()))
    try:
        topo = LiveTopology(str(tmp_path)).topology()
    finally:
        live_snmp.clear_cache()
    assert topo.source == "live"
    assert [n.id for n in topo.nodes] == ["lab-cisco1", "lab-junos1"]
    assert len(topo.links) == 1 and topo.links[0].util_pct == 1.0


def test_polled_at_formats():
    assert live_snmp.polled_at({"polled_at": 1_795_627_800_000}) == 1_795_627_800
    assert live_snmp.polled_at({"polled_at": 1_795_627_800}) == 1_795_627_800
    assert live_snmp.polled_at({"polled_at": "1795627800000"}) == 1_795_627_800
    iso = live_snmp.polled_at({"polled_at": "bad", "timestamp": "2026-11-25T17:30:00.123456789Z"})
    assert iso == pytest.approx(1_795_627_800.123, abs=0.01)
    assert live_snmp.polled_at({"polled_at": True}) is None


def write(root, day, lines):
    folder = root / day
    folder.mkdir(parents=True)
    (folder / live_snmp.FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_reads_only_the_tail_and_yesterday_when_today_is_short(tmp_path, monkeypatch):
    assert live_snmp.read_lines(tmp_path / "missing") == []
    assert live_snmp.read_lines(tmp_path) == []
    write(tmp_path, "2026-11-24", ["old-1", "old-2", "old-3"])
    write(tmp_path, "2026-11-25", ["new-1", "new-2"])
    (tmp_path / "not-a-day").mkdir()
    assert live_snmp.read_lines(tmp_path) == ["old-1", "old-2", "old-3", "new-1", "new-2"]
    monkeypatch.setattr(live_snmp, "READ_BUDGET", 18)  # today's 12 bytes + 6 of yesterday's
    assert live_snmp.read_lines(tmp_path) == ["new-1", "new-2"]  # cut line dropped


@pytest.fixture
def ingest(tmp_path, monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "dev")
    monkeypatch.setenv("MONICOMM_DEMO_DATA", "true")
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "ollama")
    monkeypatch.setenv("MONICOMM_INVESTIGATOR_INGEST_DIR", str(tmp_path))
    monkeypatch.setattr(live_snmp, "_clock", lambda: NOW)
    write(tmp_path, "2026-11-25", lab_lines())
    get_settings.cache_clear()
    live_snmp.clear_cache()
    yield tmp_path
    get_settings.cache_clear()
    live_snmp.clear_cache()


def names(path):
    res = client.get(path)
    assert res.status_code == 200
    return res.json()


def test_demo_mode_combines_demo_and_live(ingest):
    body = names("/api/v1/dashboard/devices")
    found = {d["name"] for d in body["items"]}
    assert body["source"] == "demo"
    assert {"lab-cisco1", "lab-junos1", "DEMO-core-sw-01"} <= found
    assert names(f"/api/v1/dashboard/devices/live-{CISCO}")["device"]["name"] == "lab-cisco1"
    topo = names("/api/v1/mapper/topology")
    assert {n["name"] for n in topo["nodes"]} >= {"lab-cisco1", "DEMO-core-sw-01"}
    assert any(link["id"].startswith(f"live-{CISCO}:Gi0/1") for link in topo["links"])
    analyzer = names("/api/v1/analyzer/impact/topology")
    assert {"lab-cisco1", "DEMO-core-sw-01"} <= {n["id"] for n in analyzer["nodes"]}


def test_live_only_outside_demo_mode(ingest, monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "prod")
    get_settings.cache_clear()
    body = names("/api/v1/dashboard/devices")
    assert body["source"] == "live" and body["total"] == 2
    assert names("/api/v1/mapper/topology")["source"] == "live"
    assert names("/api/v1/analyzer/impact/topology")["source"] == "live"


def test_empty_ingest_dir_is_no_devices_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("MONICOMM_ENV", "prod")
    monkeypatch.setenv("MONICOMM_INVESTIGATOR_INGEST_DIR", str(tmp_path / "nothing-yet"))
    get_settings.cache_clear()
    live_snmp.clear_cache()
    try:
        assert names("/api/v1/dashboard/summary")["devices"]["total"] == 0
        assert names("/api/v1/mapper/topology")["nodes"] == []
    finally:
        get_settings.cache_clear()
        live_snmp.clear_cache()


def test_cloud_model_never_sees_live_devices(ingest, monkeypatch):
    seen = []

    async def fake(messages):
        seen.append(messages)
        return "ok"

    monkeypatch.setattr(llm_client, "chat", fake)
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "gemini")
    get_settings.cache_clear()
    res = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "status?"}]})
    assert res.status_code == 200
    sent = seen[0][-1]["content"]
    assert "DEMO-core-sw-01" in sent and "lab-cisco1" not in sent


def test_demo_only_views():
    combined = CombinedSource(DemoSource(), LiveSource("unused"))
    assert without_live(combined) is combined.demo
    assert without_live(LiveSource("unused")) is None
    demo = DemoSource()
    assert without_live(demo) is demo


def test_analyzer_model_view(monkeypatch):
    monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "gemini")
    get_settings.cache_clear()
    try:
        combined = CombinedTopology(DemoTopology(), LiveTopology("unused"))
        assert analyzer_service.for_model(combined) is combined.demo
        demo = DemoTopology()
        assert analyzer_service.for_model(demo) is demo
        with pytest.raises(analyzer_service.ExternalModelRefused):
            analyzer_service.for_model(LiveTopology("unused"))
        monkeypatch.setenv("MONICOMM_LLM_PROVIDER", "ollama")
        get_settings.cache_clear()
        live = LiveTopology("unused")
        assert analyzer_service.for_model(live) is live
    finally:
        get_settings.cache_clear()
