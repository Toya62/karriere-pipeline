"""Tests for resume parsing and AI profile extraction module."""

import io
import pytest
from unittest.mock import MagicMock, patch

from src.ai.resume_parser import (
    extract_text_from_pdf,
    parse_resume_with_ai,
    ResumeParseError,
)


def _make_dummy_pdf_bytes(text: str = "Candidate Name\nMechanical Engineer\nExperience: CAD Design") -> bytes:
    """Generate minimal valid PDF in memory for tests."""
    from pdfminer.pdfdocument import PDFDocument
    # Return minimal binary with text or read an existing small PDF
    try:
        import pypdf
        writer = pypdf.PdfWriter()
        writer.add_blank_page(width=72, height=72)
        stream = io.BytesIO()
        writer.write(stream)
        return stream.getvalue()
    except Exception:
        # Fallback to minimal PDF header/trailer
        return b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"


def test_extract_text_from_invalid_pdf():
    """Invalid or empty bytes should raise ResumeParseError."""
    with pytest.raises(ResumeParseError):
        extract_text_from_pdf(b"Not a real pdf at all")


def test_extract_text_from_valid_pdf():
    """Valid PDF extracts non-empty string."""
    fake_page = MagicMock()
    fake_page.extract_text.return_value = "Candidate Name\nSenior Backend Engineer with Python, FastAPI, and PostgreSQL."
    fake_pdf = MagicMock()
    fake_pdf.pages = [fake_page]
    fake_pdf.__enter__.return_value = fake_pdf

    with patch("pdfplumber.open", return_value=fake_pdf):
        dummy_pdf_bytes = b"%PDF-1.4 minimal valid test pdf byte stream"
        text = extract_text_from_pdf(dummy_pdf_bytes)
        assert isinstance(text, str)
        assert "Backend Engineer" in text
        assert len(text.strip()) > 50


def test_parse_resume_with_ai_success():
    """Mock AI Router returns structured candidate profile and recommendations."""
    sample_text = (
        "Alex Schmidt\nalex@example.com\nBerlin, Germany\n"
        "Mechanical Design Engineer with 4 years CAD and Finite Element Analysis.\n"
        "Experience: Senior CAD Engineer at AutoWerke GmbH (2021 - 2024)\n"
        "Education: B.Sc. Mechanical Engineering, RWTH Aachen (2020)\n"
        "Skills: SolidWorks, CATIA, ANSYS, Python, German C1, English C1"
    )

    fake_ai_response = {
        "personal_info": {
            "name": "Alex Schmidt",
            "email": "alex@example.com",
            "phone": "+49 170 1234567",
            "location": "Berlin, Germany",
            "relocation": "Ready to relocate",
            "linkedin": "linkedin.com/in/alexschmidt",
            "github": "",
        },
        "target_titles": [
            "Mechanical Design Engineer",
            "CAD Development Engineer",
            "Finite Element Analysis Specialist",
        ],
        "archetype": "mechanical_engineering",
        "experience_summary": "Mechanical Design Engineer with 4 years experience in SolidWorks, CATIA and ANSYS.",
        "education": [
            {
                "degree": "B.Sc. Mechanical Engineering",
                "university": "RWTH Aachen",
                "graduation_year": "2020",
                "details": "Major in automotive structural mechanics.",
            }
        ],
        "experience": [
            {
                "role": "Senior CAD Engineer",
                "company": "AutoWerke GmbH",
                "period": "2021 - 2024",
                "description": "Led mechanical CAD design for chassis components.",
            }
        ],
        "skills": {
            "CAD_and_Simulation": ["SolidWorks", "CATIA", "ANSYS"],
            "Languages": ["Python"],
        },
        "languages": {
            "Deutsch": "C1",
            "Englisch": "C1",
        },
        "recommended_filters": {
            "branch": "Mechanical & Automotive Engineering",
            "titles": ["Mechanical Design Engineer", "CAD Engineer", "FEA Specialist"],
            "suggested_countries": ["Germany", "Austria", "Switzerland"],
            "default_mode": "hybrid",
        },
    }

    with patch("src.ai.resume_parser.extract_text_from_pdf", return_value=sample_text):
        with patch("src.ai.resume_parser.route_ai_evaluation", return_value=fake_ai_response):
            result = parse_resume_with_ai(b"%PDF-1.4...")
            assert result["personal_info"]["name"] == "Alex Schmidt"
            assert "Mechanical Design Engineer" in result["target_titles"]
            assert result["archetype"] == "mechanical_engineering"
            assert len(result["experience"]) == 1
            assert result["recommended_filters"]["branch"] == "Mechanical & Automotive Engineering"
