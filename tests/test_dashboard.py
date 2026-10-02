import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import src.dashboard.server as server

def test_dashboard_server_imports():
    """Verify that the dashboard server module can be imported successfully."""
    assert hasattr(server, 'run')
    assert hasattr(server, 'DashboardHandler')
