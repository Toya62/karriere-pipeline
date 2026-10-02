"""
src/core package
Provides configuration, filtering rules, logger, archetype matching, and utilities.
"""

from src.core.logger import get_logger
from src.core.config import get_window_tag, get_max_days
from src.core.profile_matcher import ProfileMatcher

__all__ = [
    "get_logger",
    "get_window_tag",
    "get_max_days",
    "ProfileMatcher",
]
