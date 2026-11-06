import os
import tempfile
import pytest
from src.generators.compiler import _proofread_german_cover, _sanitize_tex_file


def test_proofread_german_cover_verb_agreement():
    raw_tex = r"""Sehr geehrte Frau Müller,

Für Ihre Plattform bringe ich Expertise mit.
Während meiner Tätigkeit verfolgen ich agile Prozesse und entwickeln ich Backend-Services.
Dabei haben ich automatisierte Tests aufgebaut und konnten ich CI/CD-Pipelines optimieren.
Später unterstützen ich das Team und optimieren ich Datenbankabfragen.
"""
    cleaned, fixes = _proofread_german_cover(raw_tex)

    assert "verfolge ich" in cleaned
    assert "verfolgen ich" not in cleaned
    assert "entwickle ich" in cleaned
    assert "entwickeln ich" not in cleaned
    assert "habe ich" in cleaned
    assert "haben ich" not in cleaned
    assert "konnte ich" in cleaned
    assert "konnten ich" not in cleaned
    assert "unterstütze ich" in cleaned
    assert "unterstützen ich" not in cleaned
    assert "optimiere ich" in cleaned
    assert "optimieren ich" not in cleaned
    assert fixes >= 6


def test_proofread_german_cover_removes_banned_openings():
    raw_tex = r"""Sehr geehrte Damen und Herren,

mit großem Interesse bewerbe ich mich auf die Position als Backend Developer.
Für Ihre Cloud-Infrastruktur bringe ich fundierte Python-Kenntnisse mit.
"""
    cleaned, fixes = _proofread_german_cover(raw_tex)

    assert "mit großem Interesse" not in cleaned
    assert "Mit großem Interesse" not in cleaned
    assert "Für Ihre Cloud-Infrastruktur bringe ich fundierte Python-Kenntnisse mit." in cleaned
    assert fixes >= 1


def test_proofread_german_cover_capitalizes_sentence_starting_ich():
    raw_tex = r"""Sehr geehrte Damen und Herren,

Für Ihre Plattform bringe ich Expertise mit. ich freue mich über das Gespräch.
ich stehe für eine bundesweite Tätigkeit bereit.
"""
    cleaned, fixes = _proofread_german_cover(raw_tex)

    assert "Ich freue mich über das Gespräch." in cleaned
    assert "Ich stehe für eine bundesweite Tätigkeit bereit." in cleaned


def test_sanitize_tex_file_runs_german_proofreading_on_cover_file():
    raw_tex = r"""\documentclass{article}
\begin{document}
Sehr geehrte Damen und Herren,

mit großem Interesse verfolgen ich die Entwicklung Ihrer Systeme.
Für Ihre Pipeline bringe ich zwei Schwerpunkte mit.

Mit freundlichen Grüßen,
Toyanath Pandey
\end{document}
"""
    with tempfile.NamedTemporaryFile("w", suffix="_cover.tex", delete=False) as f:
        f.write(raw_tex)
        temp_path = f.name

    try:
        _sanitize_tex_file(temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            sanitized = f.read()

        assert "mit großem Interesse" not in sanitized
        assert "verfolgen ich" not in sanitized
        assert "verfolge ich" in sanitized or "Für Ihre Pipeline bringe ich" in sanitized
        assert r"\spaceskip=3.8pt" in sanitized
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_sanitize_tex_file_ignores_english_cover_letter_for_german_pass():
    raw_tex = r"""\documentclass{article}
\begin{document}
Dear Hiring Team,

For your backend platform, I bring two core strengths: Python and Docker.
I look forward to discussing how my experience fits the role.

Kind regards,
Toyanath Pandey
\end{document}
"""
    with tempfile.NamedTemporaryFile("w", suffix="_cover.tex", delete=False) as f:
        f.write(raw_tex)
        temp_path = f.name

    try:
        _sanitize_tex_file(temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            sanitized = f.read()

        assert "Dear Hiring Team," in sanitized
        assert "Kind regards," in sanitized
        assert r"\spaceskip=3.8pt" in sanitized
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
