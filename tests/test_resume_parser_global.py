"""Unit tests for international resume location extraction (Canada, US, Nepal, Germany)."""

import pytest
from src.ai.resume_parser import extract_location_preferences_from_text


def test_extract_canadian_resume_location():
    text = """
    Jane Doe
    Toronto, Ontario, Canada | jane.doe@example.com | (416) 555-0199
    Senior Full Stack Engineer with 4 years experience in TypeScript and React.
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Canada" in prefs["countries"]
    assert any("toronto" in c.lower() for c in prefs["cities"])


def test_extract_nepal_resume_location():
    text = """
    Aarav Sharma
    Kathmandu, Nepal | aarav@example.com
    Backend Developer specializing in Python, FastAPI and PostgreSQL.
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Nepal" in prefs["countries"]
    assert any("kathmandu" in c.lower() for c in prefs["cities"])


def test_extract_us_resume_location():
    text = """
    Michael Scott
    Scranton, Pennsylvania, United States | michael@dundermifflin.com
    Regional Manager & Sales Engineer.
    """
    prefs = extract_location_preferences_from_text(text)
    assert "United States" in prefs["countries"]


def test_extract_germany_resume_location():
    text = """
    Toyanath Pandey
    Essen, Germany | toya@example.com
    Software Systems Engineer
    """
    prefs = extract_location_preferences_from_text(text)
    assert "Germany" in prefs["countries"]
