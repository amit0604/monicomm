"""Change impact data source and report store selection."""

from app.ai import llm_settings
from app.core import data_sources
from app.core.config import get_settings
from app.modules.analyzer.live import CombinedTopology, LiveTopology
from app.modules.analyzer.models import TopologySource
from app.modules.analyzer.store import ReportStore


class NoDataSource(RuntimeError):
    """No topology source is configured."""


class ExternalModelRefused(RuntimeError):
    """A model outside the closed network may only see demo data."""


def get_source() -> TopologySource:
    """Demo, live or both: the shared rule in app.core.data_sources."""
    from app.modules.analyzer.demo import DemoTopology

    source = data_sources.choose(DemoTopology, LiveTopology, CombinedTopology)
    if source is None:
        raise NoDataSource
    return source


def for_model(source: TopologySource) -> TopologySource:
    """What the change parser may show the model: a cloud model (dev-only gemini) gets demo only."""
    if llm_settings.current().llm_provider != "gemini":
        return source
    if isinstance(source, CombinedTopology):
        return source.demo
    if getattr(source, "source", None) == "demo":
        return source
    raise ExternalModelRefused


def get_store() -> ReportStore:
    settings = get_settings()
    return ReportStore(settings.analyzer_data_dir)
