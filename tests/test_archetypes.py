"""Unit tests for domain archetype catalog."""

import pytest
from src.core.archetypes import DomainArchetype, get_archetype, list_archetypes


def test_get_civil_engineering_archetype():
    arch = get_archetype("civil_engineering")
    assert isinstance(arch, DomainArchetype)
    assert arch.slug == "civil_engineering"
    assert "Bauingenieur" in arch.target_titles
    assert "Tragwerksplaner" in arch.target_titles
    assert any("statik" in k.lower() for k in arch.relevance_keywords)
    # Check that civil engineering does not have CS mandatory keywords
    assert "python" not in [k.lower() for k in arch.relevance_keywords]


def test_get_mechanical_engineering_archetype():
    arch = get_archetype("mechanical_engineering")
    assert arch.slug == "mechanical_engineering"
    assert "Konstrukteur" in arch.target_titles
    assert any("cad" in k.lower() for k in arch.relevance_keywords)


def test_get_data_engineering_archetype():
    arch = get_archetype("data_engineering")
    assert arch.slug == "data_engineering"
    assert "Data Engineer" in arch.target_titles
    assert any("etl" in k.lower() for k in arch.relevance_keywords)


def test_unknown_archetype_falls_back_to_general():
    arch = get_archetype("quantum_gardening_unknown")
    assert arch.slug == "general_engineering"
    assert len(arch.target_titles) > 0


def test_list_archetypes_returns_all_catalogs():
    all_archs = list_archetypes()
    slugs = [a.slug for a in all_archs]
    assert "civil_engineering" in slugs
    assert "mechanical_engineering" in slugs
    assert "electrical_engineering" in slugs
    assert "data_engineering" in slugs
    assert "backend_platform" in slugs
    assert "devsecops" in slugs
    assert "general_engineering" in slugs
