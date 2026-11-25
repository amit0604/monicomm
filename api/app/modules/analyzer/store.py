"""Impact report storage: one JSON file per report under <data_dir>/reports/<id>.json."""

import logging
import os
import re
import tempfile
from pathlib import Path

from pydantic import ValidationError

from app.modules.analyzer.models import Report, ReportSummary

ID_RE = re.compile(r"imp-\d{8}-[0-9a-f]{6}")  # used with fullmatch
log = logging.getLogger(__name__)


class ReportStore:
    def __init__(self, data_dir: str | Path):
        self.dir = Path(data_dir) / "reports"

    def _path(self, report_id: object) -> Path | None:
        # checked before any filesystem access: the id comes from the URL (path traversal)
        if not isinstance(report_id, str) or not ID_RE.fullmatch(report_id):
            return None
        return self.dir / f"{report_id}.json"

    def save(self, report: Report) -> None:
        path = self._path(report.id)
        if path is None:
            raise ValueError("invalid report id")
        self.dir.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.dir, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(report.model_dump_json(indent=1))
            os.replace(tmp, path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def get(self, report_id: str) -> Report | None:
        path = self._path(report_id)
        if path is None or not path.is_file():
            return None
        return _load(Report, path)

    def list(self) -> list[ReportSummary]:
        """Newest first. ponytail: reads every file, add an index past ~10k reports."""
        if not self.dir.is_dir():
            return []
        items = [
            _load(ReportSummary, p) for p in self.dir.glob("*.json") if ID_RE.fullmatch(p.stem)
        ]
        return sorted((i for i in items if i), key=lambda r: r.created_at, reverse=True)


def _load[M: (Report, ReportSummary)](model: type[M], path: Path) -> M | None:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        log.warning("skipping unreadable report file %s", path.name)  # name only, no content
        return None
