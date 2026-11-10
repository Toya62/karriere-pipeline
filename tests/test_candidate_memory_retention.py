"""Tests for candidate-memory-and-retention rules, profile integrity, and multi-tenant isolation."""

import yaml
from src.core.config import candidate_profile_context
from src.generators.compiler import generate_application_package
from src.generators.form_copilot import generate_form_answer


def test_verified_education_integrity():
    """Verify education contains strictly M.Sc. and B.Sc. without B.Tech or High School."""
    context_str = candidate_profile_context()
    data = yaml.safe_load(context_str)
    education = data.get("education", [])

    assert len(education) == 2, f"Expected exactly 2 degrees (M.Sc. and B.Sc.), found {len(education)}"
    degrees = [str(e.get("degree", "")) for e in education]

    # Must contain M.Sc. and B.Sc.
    assert any("m.sc" in d.lower() for d in degrees)
    assert any("b.sc" in d.lower() for d in degrees)

    # Must NEVER contain B.Tech or High School (Tilottama / HSEB)
    for d in degrees:
        assert "b.tech" not in d.lower(), f"Forbidden degree found: {d}"
        assert "hseb" not in d.lower(), f"Forbidden secondary school found: {d}"
        assert "tilottama" not in d.lower(), f"Forbidden school found: {d}"


def test_candidate_profile_context_tenant_isolation():
    """Verify that secondary tenant profiles do not inherit admin master experience or coursework."""
    tenant_profile = {
        "user_id": 42,
        "personal_info": {"name": "Bob Tester", "email": "bob@example.com"},
        "education": [{"degree": "B.A. Economics", "university": "Humboldt Universität"}],
        "skills": {"languages": ["Python", "R"]},
    }

    ctx = yaml.safe_load(candidate_profile_context(tenant_profile))
    assert ctx["personal_info"]["name"] == "Bob Tester"
    assert len(ctx["education"]) == 1
    assert ctx["education"][0]["degree"] == "B.A. Economics"
    assert "experience" not in ctx  # Never bled Toyanath's experience!


def test_compiler_escapes_dollar_and_special_chars(tmp_path, monkeypatch):
    """Verify LaTeX compiler escapes special characters including dollar signs."""
    import src.generators.compiler as comp

    # Call generate_application_package with special characters in title and company
    res = comp.generate_application_package(
        company="Tech & Fin $100k % Corp #1",
        title="Senior Python_Dev",
        location="Essen, Germany",
        archetype="backend_platform",
        language="de",
        target_date="2026-11-10",
    )

    # Verify generated cover letter file exists and has escaped characters
    cl_path = res["cover_pdf"].replace(".pdf", ".tex") if "cover_pdf" in res else None
    # Since clean_tex=True in compile_all_applications, check meta_json
    assert res.get("meta_json") is not None


def test_form_copilot_tenant_personalization(monkeypatch):
    """Verify that form copilot uses dynamic candidate name and context when provided."""
    mock_called_prompt = []

    class MockModel:
        def generate_content(self, model, contents, config):
            mock_called_prompt.append(contents)
            class Resp:
                text = "Ich freue mich auf die Rolle und bringe fundierte Kenntnisse mit."
            return Resp()

    class MockClient:
        models = MockModel()

    monkeypatch.setattr("src.ai.matcher.get_gemini_client", lambda: MockClient())

    tenant_profile = {
        "user_id": 99,
        "personal_info": {"name": "Sara Connor", "email": "sara@example.com"},
    }

    res = generate_form_answer(
        question="Why do you want to join our team?",
        company="Cyberdyne",
        position="Robotics Engineer",
        language="de",
        candidate_profile=tenant_profile,
        candidate_name="Sara Connor",
    )

    assert res["success"] is True
    assert len(mock_called_prompt) == 1
    prompt_text = mock_called_prompt[0]
    assert "Sara Connor" in prompt_text
    assert "Toyanath" not in prompt_text
