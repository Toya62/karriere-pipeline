"""Dashboard API routers.

Each module owns one resource area and is mounted by
:func:`src.dashboard.app.create_app`.
"""

from src.dashboard.routers import dismissals, documents, generation, jobs, scraper, seeds, sync, tracker

ALL_ROUTERS = [
    jobs.router,
    tracker.router,
    documents.router,
    seeds.router,
    dismissals.router,
    scraper.router,
    generation.router,
    sync.router,
]

__all__ = ["ALL_ROUTERS"]
