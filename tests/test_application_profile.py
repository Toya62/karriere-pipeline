from src.generators import application
from src.generators import email


def test_generation_prompt_uses_configured_candidate_profile_only():
    prompt = application._build_generation_prompt(
        company="Example Job",
        position="Python Developer",
        description="Build software",
        cv_template="CV layout",
        cl_template="Cover layout",
        language="en",
        agents_rules="",
        candidate_profile="Verified experience: Built a Python API at Acme.",
    )

    assert "Verified experience: Built a Python API at Acme." in prompt
    assert "Example Company A" not in prompt
    assert "All 5 verified work experiences" not in prompt


def test_installed_generator_uses_configured_template_directory(monkeypatch, tmp_path):
    template_dir = tmp_path / "user-templates"
    template_dir.mkdir()
    (template_dir / "cv_template_backend.tex").write_text("Custom CV template", encoding="utf-8")
    monkeypatch.setenv("KARRIERE_TEMPLATES_DIR", str(template_dir))

    assert application._load_template("cv_template_backend.tex") == "Custom CV template"


def test_application_generation_refuses_unconfigured_profile(monkeypatch):
    monkeypatch.setattr(application.config, "CANDIDATE_PROFILE_CONFIGURED", False)

    result = application.generate_application(
        company="Example Job",
        position="Python Developer",
        description="A sufficiently detailed job description.",
    )

    assert result["success"] is False
    assert "user_profile.yml" in result["error"]


def test_email_generation_refuses_unconfigured_profile(monkeypatch):
    monkeypatch.setattr(email.config, "CANDIDATE_PROFILE_CONFIGURED", False)

    result = email.generate_application_email(company="Example", position="Engineer")

    assert result["success"] is False
    assert "user_profile.yml" in result["error"]


def test_email_fallback_does_not_invent_candidate_claims(monkeypatch):
    monkeypatch.setattr(email.config, "CANDIDATE_PROFILE_CONFIGURED", True)
    monkeypatch.setitem(email.CANDIDATE_PROFILE, "experience", "Verified candidate experience.")
    monkeypatch.setattr(email, "find_matching_applications", lambda *args: [])
    monkeypatch.setattr(email, "lookup_job_details", lambda *args: {})
    monkeypatch.setattr("src.ai.matcher.get_gemini_client", lambda: None)

    result = email.generate_application_email(
        company="Example",
        position="Engineer",
        explicit_email="jobs@example.org",
    )

    assert result["success"] is True
    assert "Verified candidate experience." in result["body"]
    assert "M.Sc." not in result["body"]
    assert "Python" not in result["body"]
    assert "attached as PDFs" not in result["body"]
