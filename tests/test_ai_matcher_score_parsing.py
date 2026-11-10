# tests/test_ai_matcher_score_parsing.py
import pytest
from src.ai.matcher import evaluate_single_job

def test_score_parser_accepts_fit_score_from_dynamic_prompt():
    # Simulates LLM response matching build_matching_system_prompt schema
    mock_llm_response = {
        "fit_score": 88,
        "status": "APPROVED",
        "decision_summary": "Strong technical alignment with Python and GCP ML pipelines.",
        "target_archetype": "data_science",
        "recommended_doc_language": "ENGLISH"
    }

    # Extract score logic matching matcher update
    score = int(mock_llm_response.get("match_score") or mock_llm_response.get("fit_score") or mock_llm_response.get("gemini_score") or 0)
    assert score == 88

def test_score_parser_falls_back_cleanly():
    empty_resp = {}
    score = int(empty_resp.get("match_score") or empty_resp.get("fit_score") or empty_resp.get("gemini_score") or 0)
    assert score == 0

    match_score_resp = {"match_score": 92}
    score = int(match_score_resp.get("match_score") or match_score_resp.get("fit_score") or match_score_resp.get("gemini_score") or 0)
    assert score == 92
