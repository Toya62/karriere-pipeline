import pytest
from src.automation.form_filler import fuzzy_score, OPTION_SELECTORS, ATSFormFiller, load_candidate_profile


def test_fuzzy_score():
    # Exact match
    assert fuzzy_score("Germany", "Germany") == 1.0
    assert fuzzy_score("yes", "YES") == 1.0

    # Substring match
    assert fuzzy_score("Germany", "Germany (+49)") == 0.8
    assert fuzzy_score("M.Sc.", "M.Sc. Computer Science") == 0.8

    # Word overlap
    score = fuzzy_score("driver license", "valid driver license required")
    assert score >= 0.3

    # Zero overlap
    assert fuzzy_score("Python", "Java Spring Boot") == 0.0
    assert fuzzy_score("", "Germany") == 0.0


def test_option_selectors():
    assert ".select__option" in OPTION_SELECTORS
    assert '[role="option"]' in OPTION_SELECTORS
    assert "div[data-value]" in OPTION_SELECTORS


def test_candidate_profile_and_filler_init():
    candidate = load_candidate_profile()
    filler = ATSFormFiller(candidate)
    assert filler.candidate is not None
    assert "email" in filler.candidate
    assert "phone" in filler.candidate
