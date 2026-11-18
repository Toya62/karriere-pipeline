"""Tests for AI Filter Rules Extraction Engine."""

from unittest.mock import patch
import pytest

from src.ai.resume_parser import extract_filter_rules_with_ai


def test_extract_filter_rules_from_civil_engineer_resume():
    civil_resume = """
    Max Mustermann
    M.Sc. Bauingenieurwesen - RWTH Aachen
    Erfahrung: 2 Jahre Tragwerksplanung, Statikberechnung Hochbau mit AutoCAD und Revit BIM.
    Kenntnisse: Eurocode, Massivbau, Statik, Bewehrungspläne.
    """
    mock_resp = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Statiker"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM", "Eurocode", "Massivbau"],
        "exclusion_keywords": ["Dachdecker", "Maler", "Gerüstbau"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Civil engineer specializing in structural design and BIM."
    }
    with patch("src.ai.resume_parser.route_ai_evaluation", return_value=mock_resp):
        rules = extract_filter_rules_with_ai(civil_resume)
        assert rules["discipline"] == "Civil Engineering"
        assert "Bauingenieur" in rules["target_titles"]
        assert "Statik" in rules["inclusion_keywords"]
        assert "Python" not in rules["inclusion_keywords"]
        assert "Dachdecker" in rules["exclusion_keywords"]
        assert rules["min_years_experience"] == 0
        assert rules["max_years_experience"] == 3


def test_extract_filter_rules_fallback_when_ai_fails():
    resume = "John Doe\nElectrical Engineer\nEmbedded C and PCB design"
    with patch("src.ai.resume_parser.route_ai_evaluation", side_effect=RuntimeError("AI API down")):
        rules = extract_filter_rules_with_ai(resume)
        assert isinstance(rules, dict)
        assert "target_titles" in rules
        assert "inclusion_keywords" in rules
        assert "exclusion_keywords" in rules


def test_extract_filter_rules_strips_conflicting_exclusions():
    """Verify that exclusion keywords never conflict with target titles or core skills."""
    mock_resp = {
        "discipline": "Civil Engineering",
        "target_titles": ["Bauingenieur", "Tragwerksplaner", "Civil Engineer"],
        "inclusion_keywords": ["Statik", "AutoCAD", "BIM", "Eurocode"],
        "exclusion_keywords": ["Bauingenieur", "Statik", "Dachdecker", "Maler", "Gerüstbau"],
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Civil engineer.",
    }
    with patch("src.ai.resume_parser.route_ai_evaluation", return_value=mock_resp):
        rules = extract_filter_rules_with_ai("dummy text")
        # Conflicting terms must be sanitized
        assert "Bauingenieur" not in rules["exclusion_keywords"]
        assert "Statik" not in rules["exclusion_keywords"]
        assert "Dachdecker" in rules["exclusion_keywords"]


def test_extract_filter_rules_grounds_on_structured_profile():
    """Verify structured candidate_profile facts are passed to the AI prompt."""
    profile = {
        "personal_info": {"location": "Essen, Germany"},
        "education": [{"degree": "M.Sc. Mechanical Engineering", "university": "RWTH Aachen"}],
        "experience": [{"role": "CAD Designer", "company": "Bosch", "description": "SolidWorks and FEM"}],
        "skills": {"CAD": ["SolidWorks", "CATIA"], "Methods": ["FEM", "CFD"]},
        "languages": {"German": "B2", "English": "C1"},
    }
    with patch("src.ai.resume_parser.route_ai_evaluation") as mock_eval:
        mock_eval.return_value = {
            "discipline": "Mechanical Engineering",
            "target_titles": ["Maschinenbauingenieur", "CAD Konstrukteur"],
            "inclusion_keywords": ["SolidWorks", "CATIA", "FEM"],
            "exclusion_keywords": ["Call Center", "Vertrieb"],
            "seniority_level": "Junior/Mid",
            "min_years_experience": 1,
            "max_years_experience": 3,
            "summary": "Mechanical engineer.",
        }
        rules = extract_filter_rules_with_ai("", candidate_profile=profile)
        assert rules["discipline"] == "Mechanical Engineering"
        assert mock_eval.called
        call_user_prompt = mock_eval.call_args[0][1]
        assert "SolidWorks" in call_user_prompt
        assert "RWTH Aachen" in call_user_prompt


