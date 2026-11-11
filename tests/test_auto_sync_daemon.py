"""Tests for auto_sync_daemon script and CLI command."""

from unittest.mock import patch, MagicMock
from scripts.auto_sync_daemon import run_sync_cycle


def test_sync_cycle_executes_applications_pull():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "OK"
        mock_run.return_value = mock_proc

        success = run_sync_cycle(target="applications")
        assert success is True
        assert mock_run.called
        cmd = mock_run.call_args[0][0]
        assert "sync_from_server.sh" in cmd[1]
        assert cmd[2] == "applications"


def test_sync_cycle_handles_failure():
    with patch("subprocess.run") as mock_run:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stderr = "Network unreachable"
        mock_run.return_value = mock_proc

        success = run_sync_cycle(target="applications")
        assert success is False

