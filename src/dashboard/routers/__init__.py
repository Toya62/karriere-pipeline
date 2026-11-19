"""Dashboard API routers.

Each module owns one resource area and is mounted by
:func:`src.dashboard.app.create_app`.
"""

from src.dashboard.routers import application_download, auth, dismissals, documents, extension_dist, generation, jobs, scraper, seeds, sync, tracker

ALL_ROUTERS = [
    auth.router,
    jobs.router,
    tracker.router,
    documents.router,
    application_download.router,
    seeds.router,
    dismissals.router,
    scraper.router,
    generation.router,
    sync.router,
    extension_dist.router,
]

__all__ = ["ALL_ROUTERS"]
