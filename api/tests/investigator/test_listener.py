import asyncio
import json

import pytest

from app.modules.investigator.listener import Listener
from app.modules.investigator.store import IncidentStore

DAY = "2026-11-25"


def syslog(msg, ip="10.0.0.1", ts="2026-11-25T10:00:00Z"):
    return json.dumps({"kind": "syslog", "source_ip": ip, "received_at": ts, "raw": msg})


DOWN = syslog("%LINK-3-UPDOWN: Interface Gi1/0/24, changed state to down")
UP = syslog("%LINK-3-UPDOWN: Interface Gi1/0/24, changed state to up", ts="2026-11-25T10:00:05Z")
CONFIG = syslog("%SYS-5-CONFIG_I: Configured from console by admin on vty0")


class FakeTopology:
    def __init__(self):
        self.rows = []

    def update(self, metric):
        self.rows.append(metric)


class FakeCorrelator:
    def __init__(self):
        self.topology = FakeTopology()
        self.fed = []
        self.loaded = None

    def load(self, incidents):
        self.loaded = incidents

    def flush(self, now):
        self.flushed = now
        return []

    def feed(self, ev):
        self.fed.append(ev)
        if not ev.abnormal:
            return []
        return [{"id": ev.id, "status": "open", "started_at": ev.ts.isoformat(), "notes": ""}]


def write(tmp_path, name, text, day=DAY):
    path = tmp_path / "ingest" / day / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as f:
        f.write(text)


def make(tmp_path, corr=None, backfill=True):
    corr = corr or FakeCorrelator()
    listener = Listener(
        tmp_path / "ingest",
        tmp_path / "data",
        corr,
        IncidentStore(tmp_path / "data"),
        backfill=backfill,
    )
    listener.start()
    return listener, corr


def test_new_lines_fed_once_and_incident_saved(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n" + UP + "\n")
    listener, corr = make(tmp_path)
    listener.poll_once()
    assert len(corr.fed) == 2
    listener.poll_once()
    assert len(corr.fed) == 2  # nothing re-fed
    assert len(listener.store.list()) == 1


def test_resume_from_offsets_after_restart(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")
    listener, _ = make(tmp_path)
    listener.poll_once()
    incidents = listener.store.list()

    write(tmp_path, "trap.jsonl", "", day="2026-11-26")
    write(tmp_path, "syslog.jsonl", UP + "\n")
    listener2, corr2 = make(tmp_path)
    assert corr2.loaded == incidents  # open incidents handed back to the correlator
    listener2.poll_once()
    assert [e.state for e in corr2.fed] == ["up"]


def test_partial_trailing_line_waits_for_newline(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n" + UP[:20])
    listener, corr = make(tmp_path)
    listener.poll_once()
    assert len(corr.fed) == 1
    write(tmp_path, "syslog.jsonl", UP[20:] + "\n")
    listener.poll_once()
    assert [e.state for e in corr.fed] == ["down", "up"]


def test_normal_only_writes_only_offsets(tmp_path):
    write(tmp_path, "syslog.jsonl", UP + "\n" + CONFIG + "\n")
    listener, corr = make(tmp_path)
    listener.poll_once()
    assert len(corr.fed) == 2
    assert [p.name for p in (tmp_path / "data").iterdir()] == ["offsets.json"]


def test_snmp_metric_goes_to_topology(tmp_path):
    row = {"schema": "monicomm.snmp_metric.v1", "metric": "snmp_lldp_neighbor"}
    write(tmp_path, "snmp_metric.jsonl", json.dumps(row) + "\nnot json\n[1]\n")
    listener, corr = make(tmp_path)
    listener.poll_once()
    assert corr.topology.rows == [row]
    assert corr.fed == []


def test_malformed_lines_skipped(tmp_path):
    write(tmp_path, "syslog.jsonl", "garbage\n{}\n\n" + DOWN + "\n")
    write(tmp_path, "trap.jsonl", '{"kind": "trap"}\n')
    listener, corr = make(tmp_path)
    listener.poll_once()
    assert len(corr.fed) == 1


def test_user_fields_survive_correlator_update(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")
    listener, corr = make(tmp_path)
    listener.poll_once()
    inc = listener.store.list()[0]
    inc.update(notes="checked cable", status="closed")
    listener.store.save(inc)
    listener._save({"id": inc["id"], "status": "open", "notes": ""})
    saved = listener.store.get(inc["id"])
    assert (saved["notes"], saved["status"]) == ("checked cable", "closed")


def test_run_survives_errors_and_cancels(tmp_path):
    listener, corr = make(tmp_path)
    listener.poll_s = 0
    calls = []

    def boom():
        calls.append(1)
        raise RuntimeError("x")

    listener.poll_once = boom

    async def go():
        task = asyncio.create_task(listener.run())
        while len(calls) < 2:
            await asyncio.sleep(0)
        task.cancel()

    asyncio.run(go())
    assert len(calls) >= 2


# --- final review fixes --------------------------------------------------------


def test_first_start_tails_from_now_without_backfill(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")  # history already on disk
    listener, corr = make(tmp_path, backfill=False)
    listener.poll_once()
    assert corr.fed == []
    write(tmp_path, "syslog.jsonl", UP + "\n")
    listener.poll_once()
    assert len(corr.fed) == 1


def test_closed_incident_is_never_touched_again(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")
    listener, corr = make(tmp_path)
    listener.poll_once()
    inc = listener.store.list()[0]
    listener.store.save({**inc, "status": "closed", "resolution": "fixed"})
    listener._save({**inc, "status": "open"})  # correlator still thinks it's open
    assert listener.store.get(inc["id"])["status"] == "closed"
    write(tmp_path, "syslog.jsonl", UP + "\n")
    listener.poll_once()
    assert any(i["status"] == "closed" for i in corr.loaded)  # synced so it can be dropped


def test_cleared_note_stays_cleared(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")
    listener, _ = make(tmp_path)
    listener.poll_once()
    inc = listener.store.list()[0]
    listener.store.save({**inc, "notes": ""})
    listener._save({**inc, "notes": "stale copy"})
    assert listener.store.get(inc["id"])["notes"] == ""


def test_failed_poll_is_retried(tmp_path):
    write(tmp_path, "syslog.jsonl", DOWN + "\n")
    listener, corr = make(tmp_path)
    real_save = listener.store.save

    def boom(incident):
        raise OSError("disk full")

    listener.store.save = boom
    with pytest.raises(OSError):
        listener.poll_once()
    assert listener.offsets == {}
    listener.store.save = real_save
    listener.poll_once()
    assert len(listener.store.list()) == 1
