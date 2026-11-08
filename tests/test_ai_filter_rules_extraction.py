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
