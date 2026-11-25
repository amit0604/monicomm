from app.modules.investigator.topology import Topology, ifkey


def metric(device, sysname, measurement, tags=None, fields=None):
    return {
        "schema": "monicomm.snmp_metric.v1",
        "kind": "snmp_metric",
        "collector_id": "moni-snmp-01",
        "source_ip": device,
        "measurement": measurement,
        "tags": {"source": device, "sysName": sysname, **(tags or {})},
        "fields": fields or {},
        "polled_at": 1764064800000,
    }


def lldp(device, sysname, port, remote, port_id=None, port_desc=None):
    fields = {"lldpRemSysName": remote, "lldpRemChassisId": "00:11:22:33:44:55"}
    if port_id is not None:
        fields["lldpRemPortId"] = port_id
    if port_desc is not None:
        fields["lldpRemPortDesc"] = port_desc
    return metric(device, sysname, "snmp_lldp_neighbor", {"index": f"0.{port}.1"}, fields)


def iface(device, sysname, index, name):
    return metric(device, sysname, "snmp_interface", {"index": str(index), "ifName": name})


def core_topology():
    topo = Topology()
    for row in [
        iface("10.0.0.1", "core1", 24, "Gi1/0/24"),
        lldp("10.0.0.1", "core1", 24, "core2.lab.example", port_id="ge-0/0/1"),
        iface("10.0.0.2", "core2", 517, "ge-0/0/1"),
        lldp("10.0.0.2", "core2", 517, "core1", port_id="Gi1/0/24"),
        # edge1 is polled, core2 has no LLDP row for it: only the far end reports this link
        iface("10.0.0.3", "edge1", 3, "Gi0/3"),
        lldp("10.0.0.3", "edge1", 3, "core2", port_id="ge-0/0/2"),
        metric("10.0.0.3", "edge1", "snmp_identity", fields={"sysDescr": "IOS"}),
    ]:
        topo.update(row)
    return topo


def test_ifkey_matches_long_and_short_names():
    assert ifkey("GigabitEthernet1/0/24") == ifkey("Gi1/0/24") == "gi1/0/24"
    assert ifkey("ge-0/0/1") == "ge0/0/1"
    assert ifkey("Port-channel1") == ifkey("Po1")
    assert ifkey("mgmt") == "mgmt"
    assert ifkey(None) is None and ifkey("") is None


def test_link_both_directions_and_name_forms():
    topo = core_topology()
    assert topo.link("10.0.0.1", "GigabitEthernet1/0/24") == ("10.0.0.2", "ge-0/0/1")
    assert topo.link("10.0.0.2", "ge-0/0/1") == ("10.0.0.1", "Gi1/0/24")
    assert topo.link("10.0.0.1", "ifIndex 24") == ("10.0.0.2", "ge-0/0/1")
    # core2 never reported edge1: found through edge1's own LLDP row
    assert topo.link("10.0.0.2", "ge-0/0/2") == ("10.0.0.3", "Gi0/3")
    assert topo.link("10.0.0.1", "Gi1/0/1") is None
    assert topo.link("10.0.0.1", None) is None


def test_neighbors_are_symmetric_and_resolved_to_ips():
    topo = core_topology()
    assert topo.neighbors("10.0.0.1") == {"10.0.0.2"}
    assert topo.neighbors("10.0.0.2") == {"10.0.0.1", "10.0.0.3"}
    assert topo.neighbors("10.0.0.3") == {"10.0.0.2"}
    assert topo.neighbors("10.9.9.9") == set()


def test_unresolved_neighbor_keeps_sysname_and_port_fallbacks():
    topo = Topology()
    topo.update(
        lldp("10.0.0.5", "sw5", 7, "unknown-host", port_id="aa:bb:cc:dd:ee:ff", port_desc="Eth1")
    )
    topo.update(lldp("10.0.0.5", "sw5", 8, "other-host", port_id="523", port_desc=None))
    topo.update(iface("10.0.0.5", "sw5", 7, "Gi0/7"))
    topo.update(iface("10.0.0.5", "sw5", 8, "Gi0/8"))
    assert topo.neighbors("10.0.0.5") == {"unknown-host", "other-host"}
    assert topo.link("10.0.0.5", "Gi0/7") == ("unknown-host", "Eth1")  # MAC port id -> description
    assert topo.link("10.0.0.5", "Gi0/8") == ("other-host", "523")


def test_bad_rows_are_ignored():
    topo = Topology()
    topo.update({"measurement": "snmp_lldp_neighbor", "tags": {}, "fields": {}})
    topo.update(lldp("10.0.0.5", "sw5", 7, "x") | {"tags": {"source": "10.0.0.5", "index": "7"}})
    topo.update(metric("10.0.0.5", "sw5", "snmp_lldp_neighbor", {"index": "0.7.1"}, {}))
    assert topo.neighbors("10.0.0.5") == set()


def counters(device, sysname, index, name, polled_at, octets_in, octets_out, speed=1000):
    row = iface(device, sysname, index, name)
    row["fields"] = {"ifHCInOctets": octets_in, "ifHCOutOctets": octets_out}
    if speed is not None:
        row["fields"]["ifHighSpeed"] = speed
    row["polled_at"] = polled_at
    return row


def test_rate_from_last_two_samples_max_of_in_out():
    topo = Topology()
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 0, 0, 0))
    assert topo.rate("10.0.0.1", "24") is None  # one sample: no rate yet
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 60_000, 750_000_000, 1_000))
    assert topo.rate("10.0.0.1", "24") == 100_000_000.0  # 750 MB in 60 s = 100 Mbit/s
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 120_000, 750_000_000, 1_500_001_000))
    assert topo.rate("10.0.0.1", 24) == 200_000_000.0  # out is busier now, only last two kept
    assert topo.speed("10.0.0.1", "24") == 1000.0


def test_counter_wrap_reset_and_bad_time_give_no_rate():
    topo = Topology()
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 0, 5_000, 5_000))
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 60_000, 10, 6_000))  # reset
    assert topo.rate("10.0.0.1", "24") is None
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 60_000, 20, 7_000))  # same time
    assert topo.rate("10.0.0.1", "24") is None


def test_missing_or_zero_speed_is_none():
    topo = Topology()
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 0, 0, 0, speed=None))
    assert topo.speed("10.0.0.1", "24") is None
    topo.update(counters("10.0.0.1", "core1", 25, "Gi1/0/25", 0, 0, 0))
    topo.update(counters("10.0.0.1", "core1", 25, "Gi1/0/25", 60_000, 0, 0, speed=0))
    assert topo.speed("10.0.0.1", "25") is None
    assert topo.rate("10.0.0.1", "25") == 0.0
    assert topo.rate("10.0.0.9", "1") is None


def test_edges_merge_both_ends():
    topo = core_topology()
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 0, 0, 0, speed=10_000))
    topo.update(counters("10.0.0.1", "core1", 24, "Gi1/0/24", 60_000, 75_000_000, 0))
    topo.update(counters("10.0.0.2", "core2", 517, "ge-0/0/1", 0, 0, 0, speed=1000))
    topo.update(counters("10.0.0.2", "core2", 517, "ge-0/0/1", 60_000, 0, 150_000_000))
    topo.update(counters("10.0.0.3", "edge1", 3, "Gi0/3", 0, 0, 0, speed=100))
    plain = [{k: v for k, v in e.items() if not k.endswith("_port")} for e in topo.edges()]
    assert plain == [
        {
            "a": "10.0.0.1",
            "a_if": "Gi1/0/24",
            "b": "10.0.0.2",
            "b_if": "ge-0/0/1",
            "speed_mbps": 1000.0,  # min of both ends
            "load_bps": 20_000_000.0,  # max of both ends
        },
        {
            # only edge1 reports it, core2's port name is unknown: kept as LLDP says
            "a": "10.0.0.2",
            "a_if": "ge-0/0/2",
            "b": "10.0.0.3",
            "b_if": "Gi0/3",
            "speed_mbps": 100.0,
            "load_bps": None,
        },
    ]
