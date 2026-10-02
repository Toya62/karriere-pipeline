"""
src/ai package
Provides AI routing, multi-provider failover, and candidate-job matching.
"""

from src.ai.router import AIRouter, get_ai_router, route_ai_evaluation
from src.ai.matcher import run_gemini_matcher, get_gemini_client

__all__ = [
    "AIRouter",
    "get_ai_router",
    "route_ai_evaluation",
    "run_gemini_matcher",
    "get_gemini_client",
]
