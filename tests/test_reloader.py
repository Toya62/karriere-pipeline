"""Tests for the development file watcher (src/dashboard/reloader.py)."""

import os

from src.dashboard.reloader import _changed_files, _snapshot


def test_snapshot_tracks_source_and_ignores_artifacts(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.py").write_text("x = 1")
    (src / "b.log").write_text("noise")
    cache = src / "__pycache__"
    cache.mkdir()
    (cache / "a.pyc").write_text("x")

    snap = _snapshot(str(tmp_path))

    assert any(p.endswith("a.py") for p in snap)
    assert not any(p.endswith("b.log") for p in snap)
    assert not any("__pycache__" in p for p in snap)


def test_changed_files_detects_mtime_change(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    f = src / "a.py"
    f.write_text("x = 1")

    before = _snapshot(str(tmp_path))
    os.utime(f, (0, 0))
    after = _snapshot(str(tmp_path))

    changed = _changed_files(before, after)
    assert any(p.endswith("a.py") for p in changed)
