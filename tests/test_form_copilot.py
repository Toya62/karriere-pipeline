"""Tests for the Application Form Copilot."""

from unittest.mock import MagicMock, patch
from src.generators.form_copilot import _detect_language, generate_form_answer


def test_detect_language():
    assert _detect_language("Warum möchten Sie bei uns arbeiten?") == "de"
    assert _detect_language("Describe your past experience with CI/CD and Docker.") == "en"
    assert _detect_language("Unclear text", default="de") == "de"


def test_generate_form_answer_empty_question():
    res = generate_form_answer(question="")
    assert res["success"] is False
    assert "empty" in res["error"].lower()


@patch("src.ai.matcher.get_gemini_client")
def test_generate_form_answer_mocked_gemini(mock_client_fn):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Mit meinem fundierten Hintergrund in Python und CI/CD bei Bosch Engineering passe ich hervorragend zu Ihren Anforderungen."
    mock_client.models.generate_content.return_value = mock_response
    mock_client_fn.return_value = mock_client

    res = generate_form_answer(
        question="Warum möchten Sie bei uns arbeiten?",
        company="Schmitt Engineering",
        position="Test Automation Engineer",
        description="CI/CD Python Jenkins",
    )
    assert res["success"] is True
    assert "Bosch Engineering" in res["answer"]
    assert res["language"] == "de"
