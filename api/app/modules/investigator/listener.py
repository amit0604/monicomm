"""Tail the dev-ingest JSONL tree and feed the correlator.

Reads <ingest_dir>/<YYYY-MM-DD>/{syslog,trap,snmp_metric}.jsonl by byte offset; offsets are kept in
<data_dir>/offsets.json so a restart does not re-feed lines. Never logs event contents.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from .events import parse_line
from .store import IncidentStore, write_json

log = logging.getLogger(__name__)

FILES = ("snmp_metric.jsonl", "syslog.jsonl", "trap.jsonl")  # topology first
USER_FIELDS = ("notes", "resolution", "analysis")


class Listener:
    def __init__(self, ingest_dir, data_dir, correlator, store: IncidentStore, poll_s=5.0):
        self.ingest_dir = Path(ingest_dir)
        self.offsets_path = Path(data_dir) / "offsets.json"
        self.correlator = correlator
        self.store = store
        self.poll_s = poll_s
        self.offsets: dict[str, int] = {}

    def start(self) -> None:
        if self.offsets_path.is_file():
            self.offsets = json.loads(self.offsets_path.read_text(encoding="utf-8"))
        self.correlator.load([i for i in self.store.list() if i.get("status") != "closed"])

    def _read_new(self, path: Path) -> list[str]:
        key = path.relative_to(self.ingest_dir).as_posix()
        start = self.offsets.get(key, 0)
        if path.stat().st_size <= start:
            return []
        with path.open("rb") as f:
            f.seek(start)
            data = f.read()
        end = data.rfind(b"\n") + 1  # leave a partial last line for the next poll
        if end == 0:
            return []
        self.offsets[key] = start + end
        return data[:end].decode("utf-8", errors="replace").splitlines()

    def poll_once(self) -> None:
        before = dict(self.offsets)
        events = []
        if self.ingest_dir.is_dir():
            # ponytail: stats every date dir each poll; prune old days if the tree gets large
            for day in sorted(p for p in self.ingest_dir.iterdir() if p.is_dir()):
                for name in FILES:
                    path = day / name
                    if not path.is_file():
                        continue
                    for line in self._read_new(path):
                        if name == "snmp_metric.jsonl":
                            self._metric(line)
                        elif ev := parse_line(line):
                            events.append(ev)
        for ev in sorted(events, key=lambda e: e.ts):
            for incident in self.correlator.feed(ev):
                self._save(incident)
        # release held LINEPROTO downs on a quiet network (received_at is close to wall clock)
        for incident in self.correlator.flush(datetime.now(UTC)):
            self._save(incident)
        if self.offsets != before:
            write_json(self.offsets_path, self.offsets)

    def _metric(self, line: str) -> None:
        try:
            obj = json.loads(line)
        except ValueError:
            return
        if isinstance(obj, dict):
            self.correlator.topology.update(obj)

    def _save(self, incident: dict) -> None:
        """Keep what the technician wrote (notes, resolution, analysis, closed)."""
        old = self.store.get(incident.get("id"))
        if old:
            incident = dict(incident)
            for key in USER_FIELDS:
                if old.get(key):
                    incident[key] = old[key]
            if old.get("status") == "closed":
                incident["status"] = "closed"
        self.store.save(incident)

    async def run(self) -> None:
        self.start()
        while True:
            try:
                # ponytail: sync file I/O on the event loop keeps store writes single-threaded
                # (no lock with the router); move to a worker if polls get slow
                self.poll_once()
            except Exception as exc:  # keep listening; log the error type only, never event data
                log.error("investigator poll failed: %s", type(exc).__name__)
            await asyncio.sleep(self.poll_s)
