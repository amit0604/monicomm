import pytest

from app.core import live_snmp
from app.core.snmp_names import ifkey, octet_rate, remote_port, short_name
from app.modules.mapper.live import links_from


def test_ifkey_and_short_name():
    assert ifkey("GigabitEthernet1/0/24") == ifkey("Gi1/0/24") == "gi1/0/24"
    assert ifkey(None) is None and ifkey("eth0") == "et0"
    assert short_name("R1.example.net") == short_name("r1") == "r1"


@pytest.mark.parametrize(
    ("port_id", "desc", "expected"),
    [
        ("Gi0/1", "uplink", "Gi0/1"),
        ("aa:bb:cc:dd:ee:ff", "ge-0/0/0", "ge-0/0/0"),  # a MAC is no port name
        ("5", "GigabitEthernet0/5", "GigabitEthernet0/5"),  # a bare number neither
        ("5", "", "5"),
        (None, None, None),
    ],
)
def test_remote_port(port_id, desc, expected):
    assert remote_port(port_id, desc) == expected


def test_octet_rate():
    assert octet_rate(0, 1000, 10, 2250) == 1000.0
    assert octet_rate(0, 1000, 10, 10) is None  # counter wrap or reset
    assert octet_rate(5, 1, 5, 2) is None


def _device(name, ports, neighbors=()):
    return live_snmp.LiveDevice(
        ip=name,
        name=name,
        up=True,
        last_poll_at=None,
        ports=[
            live_snmp.Port(str(i), p, None, True, True, 1000, 0, 0, None, None)
            for i, p in enumerate(ports, start=1)
        ],
        neighbors=list(neighbors),
    )


def test_mapper_links_use_the_investigator_name_rules():
    # LLDP says "Gi0/1" on sw2.lab; sw2 polls "GigabitEthernet0/1": one link, both names agree
    sw1 = _device(
        "sw1",
        ["Gi0/1"],
        [live_snmp.Neighbor("1", "aa:bb:cc:dd:ee:ff", "Gi0/1", "", "sw2.lab")],
    )
    sw2 = _device(
        "sw2",
        ["GigabitEthernet0/1"],
        [live_snmp.Neighbor("1", "11:22:33:44:55:66", "11:22:33:44:55:66", "Gi0/1", "sw1")],
    )
    links = links_from([sw1, sw2])
    assert [(x.a.device, x.a.port, x.b.device, x.b.port) for x in links] == [
        ("sw1", "Gi0/1", "sw2", "GigabitEthernet0/1")
    ]
