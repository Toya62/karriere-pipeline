import pytest
from unittest.mock import MagicMock, patch
from src.ai.form_resolver import resolve_form_fields, FormFieldDescriptor, FieldResolution, _repair_json_keys

def test_resolve_form_fields_with_mocked_gemini():
    fields = [
        {
            "field_id": "field_0",
            "tag": "input",
            "type": "text",
            "label": "Vorname",
            "context": "Persönliche Daten",
            "options": [],
            "required": True,
        },
        {
            "field_id": "field_1",
            "tag": "select",
            "type": "select",
            "label": "Deutschkenntnisse",
            "context": "Sprachen",
            "options": ["A1/A2", "B1", "B2 (Gute Kenntnisse)", "C1/C2 (Fließend)"],
            "required": True,
        },
        {
            "field_id": "field_2",
            "tag": "input",
            "type": "radio",
            "label": "Benötigen Sie ein Visum?",
            "context": "Rechtliche Fragen",
            "options": ["Ja", "Nein"],
            "required": True,
        }
    ]
    job_ctx = {
        "company": "Neural Frames",
        "position": "Backend Software Engineer",
        "description": "Python, FastAPI, Distributed Systems"
    }

    mock_gemini_output = """{
        "resolutions": [
            {
                "field_id": "field_0",
                "semantic_intent": "first_name",
                "action": "set_value",
                "value": "Toyanath",
                "selected_option_index": null,
                "confidence": 1.0,
                "reasoning": "Standard first name"
            },
            {
                "field_id": "field_1",
                "semantic_intent": "german_level",
                "action": "select_option",
                "value": "B2 (Gute Kenntnisse)",
                "selected_option_index": 2,
                "confidence": 0.95,
                "reasoning": "Candidate verified German level is B2"
            },
            {
                "field_id": "field_2",
                "semantic_intent": "visa_sponsorship",
                "action": "click",
                "value": "Nein",
                "selected_option_index": 1,
                "confidence": 0.98,
                "reasoning": "Candidate has valid work authorization"
            }
        ]
    }"""

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = mock_gemini_output
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        res = resolve_form_fields(fields, job_ctx)
        assert res["success"] is True
        assert len(res["resolutions"]) == 3
        assert res["resolutions"][0]["value"] == "Toyanath"
        assert res["resolutions"][1]["value"] == "B2 (Gute Kenntnisse)"
        assert res["resolutions"][1]["selected_option_index"] == 2
        assert res["resolutions"][2]["value"] == "Nein"


def test_resolve_form_fields_empty():
    res = resolve_form_fields([], {})
    assert res["success"] is True
    assert res["resolutions"] == []
    assert res["fields_count"] == 0


def test_resolve_form_fields_with_latex_and_unbalanced_json():
    """Regression test: Gemini sometimes emits raw LaTeX backslashes and
    trailing prose after the JSON object. The resolver must recover it
    instead of raising 'Expecting ',' delimiter'."""
    fields = [
        {
            "field_id": "field_0",
            "tag": "input",
            "type": "text",
            "label": "Vorname",
            "context": "Persönliche Daten",
            "options": [],
            "required": True,
        }
    ]
    job_ctx = {"company": "Neural Frames", "position": "Backend Software Engineer", "description": ""}

    # JSON with an unescaped LaTeX backslash (\textbf), markdown fences, and trailing text
    mock_gemini_output = """```json
{
  "resolutions": [
    {
      "field_id": "field_0",
      "semantic_intent": "first_name",
      "action": "set_value",
      "value": "Toyanath \\textbf{Pandey}",
      "selected_option_index": null,
      "confidence": 1.0,
      "reasoning": "Standard first name"
    }
  ]
}
Here is some extra explanation that follows the JSON object."""

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = mock_gemini_output
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        res = resolve_form_fields(fields, job_ctx)
        assert res["success"] is True
        assert len(res["resolutions"]) == 1
        assert res["resolutions"][0]["value"] == "Toyanath \\textbf{Pandey}"


def test_resolve_form_fields_failure_propagates_error():
    """If Gemini returns unparseable text after all recovery attempts, the
    resolver must surface a descriptive error instead of crashing."""
    fields = [
        {
            "field_id": "field_0",
            "tag": "input",
            "type": "text",
            "label": "Vorname",
            "context": "",
            "options": [],
            "required": True,
        }
    ]
    job_ctx = {"company": "X", "position": "Y", "description": ""}

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = "not json at all, just prose"
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        res = resolve_form_fields(fields, job_ctx)
        assert res["success"] is False
        assert res["error"] is not None
        assert "Failed to resolve form fields" in res["error"]


def test_resolve_form_fields_with_bare_keys_and_trailing_commas():
    """Regression: LLMs emit bare property names and trailing commas,
    producing 'Expecting property name enclosed in double quotes'."""
    fields = [
        {
            "field_id": "field_0",
            "tag": "input",
            "type": "text",
            "label": "Vorname",
            "context": "",
            "options": [],
            "required": True,
        }
    ]
    job_ctx = {"company": "Umantis", "position": "Backend Engineer", "description": ""}

    mock_gemini_output = """{
  resolutions: [
    {
      field_id: "field_0",
      semantic_intent: "first_name",
      action: "set_value",
      value: "Toyanath",
      selected_option_index: null,
      confidence: 1.0,
      reasoning: "Standard first name",
    }
  ]
}"""

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = mock_gemini_output
    mock_client.models.generate_content.return_value = mock_resp

    with patch("src.ai.matcher.get_gemini_client", return_value=mock_client):
        res = resolve_form_fields(fields, job_ctx)
        assert res["success"] is True
        assert len(res["resolutions"]) == 1
        assert res["resolutions"][0]["value"] == "Toyanath"
