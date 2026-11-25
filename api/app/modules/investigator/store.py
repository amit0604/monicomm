"""Incident storage: one JSON file per incident under <data_dir>/incidents/<id>.json."""

import json
import os
import re
import tempfile
from pathlib import Path

ID_RE = re.compile(r"^[0-9a-f]{12}$")


def write_json(path: Path, data: object) -> None:
    """Atomic write: temp file in the same dir, then os.replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class IncidentStore:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir) / "incidents"

    def _path(self, incident_id: object) -> Path | None:
        if not isinstance(incident_id, str) or not ID_RE.match(incident_id):
            return None
        return self.dir / f"{incident_id}.json"

    def get(self, incident_id: str) -> dict | None:
        path = self._path(incident_id)
        if path is None or not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, incident: dict) -> None:
        path = self._path(incident.get("id"))
        if path is None:
            raise ValueError("invalid incident id")
        write_json(path, incident)

    def list(self, status: str | None = None) -> list[dict]:
        """Full incidents, newest first. ponytail: reads every file, add an index past ~10k."""
        if not self.dir.is_dir():
            return []
        items = []
        for path in self.dir.glob("*.json"):
            if ID_RE.match(path.stem):
                items.append(json.loads(path.read_text(encoding="utf-8")))
        if status:
            items = [i for i in items if i.get("status") == status]
        return sorted(items, key=lambda i: i.get("started_at") or "", reverse=True)
