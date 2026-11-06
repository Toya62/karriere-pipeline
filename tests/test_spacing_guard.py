import os
import tempfile
import pytest
from src.generators.compiler import _sanitize_tex_file


def test_sanitize_tex_injects_spacing_guard_if_missing():
    tex_input = r"""\documentclass[a4paper,10pt]{article}
\usepackage{fontspec}

\begin{document}
Test content.
\end{document}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(tex_input)
        temp_path = f.name

    try:
        _sanitize_tex_file(temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            sanitized = f.read()

        assert r"\sloppy" in sanitized
        assert r"\emergencystretch=3em" in sanitized
        assert r"\spaceskip=3.8pt plus 1.2pt minus 0pt\relax" in sanitized
        assert r"\xspaceskip=3.8pt plus 1.2pt minus 0pt\relax" in sanitized
        # Ensure it appears before \begin{document}
        assert sanitized.index(r"\spaceskip=3.8pt") < sanitized.index(r"\begin{document}")
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def test_sanitize_tex_preserves_existing_spacing_guard():
    tex_input = r"""\documentclass[a4paper,10pt]{article}
\usepackage{fontspec}

\sloppy
\emergencystretch=3em
\spaceskip=3.8pt plus 1.2pt minus 0pt\relax
\xspaceskip=3.8pt plus 1.2pt minus 0pt\relax

\begin{document}
Already guarded.
\end{document}
"""
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(tex_input)
        temp_path = f.name

    try:
        _sanitize_tex_file(temp_path)
        with open(temp_path, "r", encoding="utf-8") as f:
            sanitized = f.read()

        assert sanitized.count(r"\spaceskip=3.8pt") == 1
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
