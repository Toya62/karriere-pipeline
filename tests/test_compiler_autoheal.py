"""tests/test_compiler_autoheal.py — Comprehensive tests for self-healing LaTeX compiler and Telegram alerts."""

import os
import subprocess
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from src.generators.compiler import (
    repair_tex_with_ai,
    compile_single_tex,
    compile_all_applications,
)
from src.generators.application import _compile_tex_to_pdf


SAMPLE_BROKEN_TEX = r"""\documentclass{article}
\begin{document}
Hello World with unescaped_underscore and 50% discount.
\end{document}
"""

SAMPLE_REPAIRED_TEX = r"""\documentclass{article}
\begin{document}
Hello World with unescaped\_underscore and 50\% discount.
\end{document}
"""


def test_repair_tex_with_ai_strips_fences_and_returns_clean_latex(monkeypatch):
    mock_router = MagicMock()
    mock_router.generate_content.return_value = f"```latex\n{SAMPLE_REPAIRED_TEX}\n```"
    monkeypatch.setattr("src.ai.router.get_ai_router", lambda: mock_router)

    repaired = repair_tex_with_ai("dummy.tex", SAMPLE_BROKEN_TEX, "! Missing $ inserted.")
    assert repaired is not None
    assert r"\documentclass" in repaired
    assert r"unescaped\_underscore" in repaired
    assert "```" not in repaired
    mock_router.generate_content.assert_called_once()
    args, kwargs = mock_router.generate_content.call_args
    assert "Missing $ inserted." in args[0]
    assert kwargs.get("preferred_model") == "gemini-3.5-flash-lite"
    assert kwargs.get("response_mime_type") == "text/plain"


def test_repair_tex_with_ai_rejects_non_latex_explanation(monkeypatch):
    mock_router = MagicMock()
    mock_router.generate_content.return_value = "I found the error: you need to escape the underscore with a backslash."
    monkeypatch.setattr("src.ai.router.get_ai_router", lambda: mock_router)

    repaired = repair_tex_with_ai("dummy.tex", SAMPLE_BROKEN_TEX, "! Missing $ inserted.")
    assert repaired is None


def test_compile_single_tex_direct_success_no_alerts(monkeypatch):
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(SAMPLE_REPAIRED_TEX)
        tex_path = f.name
    pdf_path = tex_path.replace(".tex", ".pdf")

    # Mock subprocess.run to simulate success and create dummy pdf
    def mock_run(cmd, *args, **kwargs):
        with open(pdf_path, "wb") as pf:
            pf.write(b"%PDF-1.4 dummy")
        return subprocess.CompletedProcess(cmd, returncode=0, stdout="Success", stderr="")

    mock_telegram = MagicMock()
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("src.core.notifier.send_telegram_alert", mock_telegram)

    try:
        res = compile_single_tex(tex_path, compiler_type="tectonic", compiler_bin="/mock/tectonic")
        assert res == pdf_path
        assert os.path.exists(pdf_path)
        # No telegram alert on clean direct success
        mock_telegram.assert_not_called()
    finally:
        for p in (tex_path, pdf_path):
            if os.path.exists(p):
                os.remove(p)


def test_compile_single_tex_auto_heals_and_alerts_telegram(monkeypatch):
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(SAMPLE_BROKEN_TEX)
        tex_path = f.name
    pdf_path = tex_path.replace(".tex", ".pdf")

    call_count = {"compiler": 0}

    def mock_run(cmd, *args, **kwargs):
        call_count["compiler"] += 1
        if call_count["compiler"] == 1:
            # First attempt fails
            return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="! Undefined control sequence.")
        else:
            # Second attempt succeeds after AI repair
            with open(pdf_path, "wb") as pf:
                pf.write(b"%PDF-1.4 dummy")
            return subprocess.CompletedProcess(cmd, returncode=0, stdout="Success", stderr="")

    mock_telegram = MagicMock()
    mock_repair = MagicMock(return_value=SAMPLE_REPAIRED_TEX)

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("src.generators.compiler.repair_tex_with_ai", mock_repair)
    monkeypatch.setattr("src.core.notifier.send_telegram_alert", mock_telegram)

    try:
        res = compile_single_tex(tex_path, compiler_type="tectonic", compiler_bin="/mock/tectonic", max_ai_retries=2)
        assert res == pdf_path
        assert call_count["compiler"] == 2
        mock_repair.assert_called_once()
        # Repaired file should be on disk
        with open(tex_path, "r", encoding="utf-8") as f:
            disk_content = f.read()
        assert r"unescaped\_underscore" in disk_content

        # Telegram success alert must be dispatched
        mock_telegram.assert_called_once()
        sent_msg = mock_telegram.call_args[0][0]
        assert "LaTeX Auto-Heal Succeeded" in sent_msg
        assert os.path.basename(tex_path) in sent_msg
    finally:
        for p in (tex_path, pdf_path):
            if os.path.exists(p):
                os.remove(p)


def test_compile_single_tex_persistent_failure_sends_telegram_error(monkeypatch):
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(SAMPLE_BROKEN_TEX)
        tex_path = f.name

    def mock_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="! Fatal LaTeX error on line 42")

    mock_telegram = MagicMock()
    # Repair returns modified text, but compiler still fails
    mock_repair = MagicMock(return_value=SAMPLE_BROKEN_TEX + "\n% modified")

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("src.generators.compiler.repair_tex_with_ai", mock_repair)
    monkeypatch.setattr("src.core.notifier.send_telegram_alert", mock_telegram)

    try:
        res = compile_single_tex(tex_path, compiler_type="tectonic", compiler_bin="/mock/tectonic", max_ai_retries=2)
        assert res is None
        # Max retries = 2 means 1 initial + 2 retry attempts = 3 total compiler runs
        assert mock_repair.call_count == 2
        # Telegram failure alert sent
        mock_telegram.assert_called_once()
        sent_msg = mock_telegram.call_args[0][0]
        assert "LaTeX Compilation Error" in sent_msg
        assert "Fatal LaTeX error on line 42" in sent_msg
        assert "Manual review required" in sent_msg
    finally:
        if os.path.exists(tex_path):
            os.remove(tex_path)


def test_compile_single_tex_raise_on_error(monkeypatch):
    with tempfile.NamedTemporaryFile("w", suffix=".tex", delete=False) as f:
        f.write(SAMPLE_BROKEN_TEX)
        tex_path = f.name

    def mock_run(cmd, *args, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="Fatal error")

    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("src.generators.compiler.repair_tex_with_ai", lambda *a, **k: None)
    monkeypatch.setattr("src.core.notifier.send_telegram_alert", MagicMock())

    try:
        with pytest.raises(RuntimeError, match="LaTeX compilation failed for"):
            compile_single_tex(
                tex_path,
                compiler_type="tectonic",
                compiler_bin="/mock/tectonic",
                max_ai_retries=0,
                raise_on_error=True,
            )
    finally:
        if os.path.exists(tex_path):
            os.remove(tex_path)


def test_compile_tex_to_pdf_delegates_to_compile_single_tex(monkeypatch):
    mock_compile = MagicMock(return_value="/path/to/test.pdf")
    monkeypatch.setattr("src.generators.compiler.compile_single_tex", mock_compile)

    res = _compile_tex_to_pdf("/path/to/test.tex")
    assert res == "/path/to/test.pdf"
    mock_compile.assert_called_once_with("/path/to/test.tex", clean_tex=False)
