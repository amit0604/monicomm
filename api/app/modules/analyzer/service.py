"""Change impact data source and report store selection."""

from app.core.config import get_settings
from app.modules.analyzer.models import TopologySource
from app.modules.analyzer.store import ReportStore


class NoDataSource(RuntimeError):
    """No topology source is configured."""


def get_source() -> TopologySource:
    """The only source so far is demo data, which must never appear on a real site."""
    settings = get_settings()
    if settings.demo_data and settings.env == "dev":
        from app.modules.analyzer.demo import DemoTopology

        return DemoTopology()
    raise NoDataSource


def get_store() -> ReportStore:
    settings = get_settings()
    return ReportStore(settings.analyzer_data_dir)
