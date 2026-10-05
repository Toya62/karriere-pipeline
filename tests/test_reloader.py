"""Tests for the development file watcher (src/dashboard/reloader.py)."""

import os
import signal
from unittest.mock import Mock, patch

import pytest

from src.dashboard import reloader
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


def test_stop_process_cleans_process_group_after_dashboard_exits():
    proc = Mock(pid=123, poll=Mock(return_value=0))

    with patch("src.dashboard.reloader.os.killpg") as killpg:
        reloader._stop_process(proc)

    killpg.assert_any_call(proc.pid, signal.SIGTERM)


def test_reload_launches_installed_main_module(monkeypatch, tmp_path):
    proc = Mock(pid=123, poll=Mock(return_value=0))
    popen = Mock(return_value=proc)
    monkeypatch.setattr(reloader.subprocess, "Popen", popen)
    monkeypatch.setattr(reloader, "_snapshot", lambda root: {})
    monkeypatch.setattr(reloader.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(reloader.os, "name", "posix")

    reloader.run_with_reload(8000, "127.0.0.1", str(tmp_path))

    args, kwargs = popen.call_args
    assert args[0][:3] == [reloader.sys.executable, "-m", "main"]
    assert args[0][3:] == ["dashboard", "--port", "8000"]
    assert kwargs["cwd"] == str(tmp_path)


def test_reload_rejects_unsupported_platform_before_spawning(monkeypatch, tmp_path):
    popen = Mock()
    monkeypatch.setattr(reloader, "_stop_process", Mock())
    monkeypatch.setattr(reloader.subprocess, "Popen", popen)
    monkeypatch.setattr(reloader.time, "sleep", lambda _: (_ for _ in ()).throw(KeyboardInterrupt()))
    monkeypatch.setattr(reloader.os, "name", "nt")

    with pytest.raises(RuntimeError, match="POSIX"):
        reloader.run_with_reload(8000, "127.0.0.1", str(tmp_path))

    popen.assert_not_called()


def test_crashed_dashboard_process_group_is_cleaned_before_respawn(monkeypatch, tmp_path):
    first = Mock(pid=123, poll=Mock(return_value=1))
    second = Mock(pid=456, poll=Mock(return_value=0))
    popen = Mock(side_effect=[first, second])
    stop_process = Mock()
    sleep_calls = 0

    def sleep(_):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 2:
            raise KeyboardInterrupt()

    monkeypatch.setattr(reloader.subprocess, "Popen", popen)
    monkeypatch.setattr(reloader, "_stop_process", stop_process)
    monkeypatch.setattr(reloader, "_snapshot", lambda root: {})
    monkeypatch.setattr(reloader.time, "sleep", sleep)
    monkeypatch.setattr(reloader.os, "name", "posix")

    reloader.run_with_reload(8000, "127.0.0.1", str(tmp_path))

    stop_process.assert_any_call(first)
    stop_process.assert_any_call(second)
