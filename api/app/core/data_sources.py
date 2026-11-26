"""Which data a module shows: one rule for the Dashboard, the Mapper and the Analyzer.

Demo data only with MONICOMM_DEMO_DATA=true and MONICOMM_ENV=dev, never on a real site. Live data
when the collectors' ingest directory is set (MONICOMM_INVESTIGATOR_INGEST_DIR). In dev with both,
the two together. Neither: None, and the module answers 503 no_data_source.
"""

from collections.abc import Callable

from app.core.config import get_settings


def choose[T](
    demo: Callable[[], T], live: Callable[[str], T], combined: Callable[[T, T], T]
) -> T | None:
    settings = get_settings()
    ingest = settings.investigator_ingest_dir
    if settings.demo_data and settings.env == "dev":
        return combined(demo(), live(ingest)) if ingest else demo()
    if ingest:
        return live(ingest)
    return None
