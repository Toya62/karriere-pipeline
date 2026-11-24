"""Regression tests for AIRouter thread-safety, JSON stack repair, and BYOK threading."""

import json
from unittest.mock import MagicMock, patch
from src.ai.router import AIRouter, route_ai_evaluation, PREFERRED_GEMINI_MODELS
from src.ai.matcher import get_thread_gemini_client


def test_preferred_models_centralized():
    assert "gemini-3.5-flash-lite" in PREFERRED_GEMINI_MODELS
    assert "gemini-3.1-flash-lite" in PREFERRED_GEMINI_MODELS
    assert "gemini-3-flash-preview" in PREFERRED_GEMINI_MODELS


def test_router_property_thread_isolation():
    router = AIRouter()
    router.last_provider_used = "provider_a"
    router.last_key_origin = "origin_a"

    assert router.last_provider_used == "provider_a"
    assert router.last_key_origin == "origin_a"


def test_route_ai_evaluation_repairs_nested_unbalanced_json():
    # Model truncated inside a nested list and object
    truncated_json = '```json\n{"summary": "Test match", "skills": ["python", "c++"], "nested": {"valid": true, "items": ["one", "two"'

    mock_router = MagicMock()
    mock_router.generate_content.return_value = truncated_json
    mock_router.last_provider_used = "gemini (gemini-3.5-flash-lite)"

    with patch("src.ai.router.get_ai_router", return_value=mock_router):
        res = route_ai_evaluation("sys", "user")
        assert res is not None
        assert res["summary"] == "Test match"
        assert res["skills"] == ["python", "c++"]
        assert res["nested"]["items"] == ["one", "two"]
        assert res["_ai_provider"] == "gemini (gemini-3.5-flash-lite)"


def test_matcher_get_thread_gemini_client_respects_keys():
    with patch("src.ai.matcher.get_gemini_client") as mock_get_client:
        mock_client_a = MagicMock(name="client_a")
        mock_client_b = MagicMock(name="client_b")
        mock_get_client.side_effect = lambda api_key=None: mock_client_a if api_key == "KEY_A" else mock_client_b

        # Request with KEY_A
        c1 = get_thread_gemini_client(api_key="KEY_A")
        assert c1 == mock_client_a

        # Request with KEY_B should not return cached client_a
        c2 = get_thread_gemini_client(api_key="KEY_B")
        assert c2 == mock_client_b
