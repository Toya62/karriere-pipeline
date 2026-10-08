"""Tests for sequential application generation queue."""

import time
from unittest.mock import patch
from src.dashboard.applications import (
    launch_application_generation,
    get_generation_queue_stats,
    _GEN_QUEUE,
)
from src.dashboard.state import APP_GEN_STATUS


def test_launch_application_generation_sequential_queue():
    # Empty existing queue
    while not _GEN_QUEUE.empty():
        try:
            _GEN_QUEUE.get_nowait()
            _GEN_QUEUE.task_done()
        except Exception:
            break

    run_order = []

    def mock_run(company, position, description, job_url, location, language, task_key):
        time.sleep(0.05)
        run_order.append(company)

    with patch("src.dashboard.applications.run_application_generation", side_effect=mock_run):
        # Enqueue 3 tasks
        res1 = launch_application_generation("CompA", "Dev", "desc "*20, "url1", "LocA", None, "comp_a_dev")
        res2 = launch_application_generation("CompB", "Dev", "desc "*20, "url2", "LocB", None, "comp_b_dev")
        res3 = launch_application_generation("CompC", "Dev", "desc "*20, "url3", "LocC", None, "comp_c_dev")

        # The first task starts immediately or is first; the subsequent ones must report queued=True
        assert res2["queued"] is True
        assert res3["queued"] is True
        assert res3["queue_position"] >= 2

        # Wait for worker to finish
        _GEN_QUEUE.join()

        # Verify they executed sequentially in FIFO order
        assert run_order == ["CompA", "CompB", "CompC"]
