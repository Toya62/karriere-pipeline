"""Unit tests for tenant-specific dynamic location and language filtering."""

import pandas as pd
from src.core.dynamic_filters import filter_tenant_location, filter_tenant_language


def test_canadian_candidate_keeps_toronto_drops_berlin():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "location": "Toronto, ON, Canada"},
        {"id": 2, "title": "Dev 2", "location": "Berlin, Germany"},
        {"id": 3, "title": "Dev 3", "location": "Remote - Canada"},
        {"id": 4, "title": "Dev 4", "location": "Kathmandu, Nepal"},
    ])
    result = filter_tenant_location(df, {"countries": ["Canada"], "cities": ["Toronto"]})
    assert set(result["id"]) == {1, 3}


def test_nepal_candidate_keeps_kathmandu_and_remote():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "location": "Kathmandu, Nepal"},
        {"id": 2, "title": "Dev 2", "location": "Pokhara, Nepal"},
        {"id": 3, "title": "Dev 3", "location": "Frankfurt, Germany"},
        {"id": 4, "title": "Dev 4", "location": "Remote Worldwide"},
    ])
    result = filter_tenant_location(df, {"countries": ["Nepal"], "cities": ["Kathmandu"]})
    assert set(result["id"]) == {1, 2, 4}


def test_dach_candidate_enforces_german_location_filter():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "location": "Essen, Germany"},
        {"id": 2, "title": "Dev 2", "location": "Toronto, Canada"},
        {"id": 3, "title": "Dev 3", "location": "Munich, Germany"},
    ])
    result = filter_tenant_location(df, {"countries": ["Germany"]})
    assert set(result["id"]) == {1, 3}


def test_language_gate_skipped_for_non_dach_markets():
    df = pd.DataFrame([
        {"id": 1, "title": "Dev 1", "description": "English only environment, no German required."},
        {"id": 2, "title": "Dev 2", "description": "Must speak fluent German (C1 verhandlungssicher)."},
    ])
    # Canadian candidate: English market, ignores German requirement gate
    res_ca = filter_tenant_language(df, {"countries": ["Canada"]})
    assert len(res_ca) == 2

    # German candidate: German B2 gate active, drops C1-exclusive German position
    res_de = filter_tenant_language(df, {"countries": ["Germany"]})
    assert len(res_de) == 1
    assert res_de.iloc[0]["id"] == 1
