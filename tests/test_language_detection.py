"""Tests for robust language detection across CV, cover letter, and email generation."""

import pytest
from src.generators.language import detect_language


def test_detect_english_standard_tech_jd():
    title = "Senior Backend Engineer"
    desc = (
        "We are looking for a backend engineer to join our platform team. "
        "You will design, build, and maintain high-performance microservices using "
        "Python, FastAPI, Docker, Kubernetes, and AWS."
    )
    assert detect_language(title, desc) == "en"


def test_detect_english_with_german_location():
    title = "Python Software Developer (m/f/d)"
    desc = (
        "Join our engineering team in Berlin or München (Hybrid). "
        "Key responsibilities include designing RESTful APIs, writing automated unit tests, "
        "and collaborating in an agile environment. Requirements: 2+ years experience in Python."
    )
    assert detect_language(title, desc) == "en"


def test_detect_german_standard_tech_jd():
    title = "Python Entwickler (m/w/d)"
    desc = (
        "Für unseren Standort in Frankfurt am Main suchen wir ab sofort einen motivierten "
        "Python-Entwickler. Ihre Aufgaben umfassen die Weiterentwicklung unserer internen Tools, "
        "Datenbankabfragen mit PostgreSQL und die Betreuung von CI/CD-Pipelines. "
        "Wir freuen uns auf Ihre aussagekräftige Bewerbung!"
    )
    assert detect_language(title, desc) == "de"


def test_detect_german_umlauts_and_sz():
    title = "Softwareentwickler C++ / Linux"
    desc = (
        "Sie verfügen über fundierte Kenntnisse in moderner Softwareentwicklung und "
        "schätzen ein kollegiales Umfeld mit flexiblen Arbeitszeiten und regelmäßiger Weiterbildung."
    )
    assert detect_language(title, desc) == "de"


def test_detect_default_on_empty():
    assert detect_language("", "") == "de"
    assert detect_language("", "", default="en") == "en"

