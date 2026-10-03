import sys
import os
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.filters import apply_filters, filter_noise

def test_filter_noise():
    df = pd.DataFrame([
        {"title": ".NET Software Engineer"},
        {"title": "Data Engineer"},
        {"title": "Fullstack React Developer"}
    ])
    res = filter_noise(df)
    assert len(res) == 1
    assert res.iloc[0]["title"] == "Data Engineer"

def test_apply_filters_unconditional_noise():
    df = pd.DataFrame([
        {
            "title": ".NET Software Engineer",
            "description": "We are looking for a C# .NET engineer with extensive knowledge in Windows desktop development and Microsoft enterprise architectures." * 2
        },
        {
            "title": "Data Engineer",
            "description": "We are seeking a proactive Data Engineer with solid experience in Python, Apache Flink, Apache Kafka, and building automated data pipelines in Linux environments." * 2
        }
    ])
    res = apply_filters(df, is_linkedin=True)
    assert len(res) == 1
    assert res.iloc[0]["title"] == "Data Engineer"

def test_user_rejection_rules():
    desc_sample = "Standard engineering job description with extensive requirements and team collaboration responsibilities across different departments." * 2
    test_jobs = pd.DataFrame([
        {"title": "Clinical CRA Monitor", "description": "GCP life sciences pharma " + desc_sample},
        {"title": "Maritime Simulation Engineer", "description": "OMNeT++ simulation " + desc_sample},
        {"title": "Data Security Architect", "description": desc_sample},
        {"title": "CSIRT Expert", "description": "CrowdStrike XDR SOAR memory forensics " + desc_sample},
        {"title": "Power Platform & AI Solutions Engineer", "description": "Power Platform D365 automation " + desc_sample},
        {"title": "Full Stack Developer", "description": "React Spring Boot .NET C# SAP ABAP " + desc_sample},
        {"title": "DevOps Engineer", "description": "C1 Deutsch fließend erforderlich " + desc_sample}
    ])
    res = apply_filters(test_jobs, is_linkedin=False)
    assert len(res) == 0


def test_compute_score_date_freshness():
    """Verify that invalid/missing dates return 0 rather than falsely scoring 25."""
    from datetime import datetime, timezone
    from src.scrapers.orchestrator import _compute_score

    assert _compute_score(None) == 0
    assert _compute_score("") == 0
    assert _compute_score("invalid-date-xyz") == 0
    assert _compute_score("NaN") == 0
    assert _compute_score("NaT") == 0

    # Real fresh date (< 24h)
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    score = _compute_score(now_iso)
    assert score >= 40, f"Expected high score for fresh date, got {score}"

