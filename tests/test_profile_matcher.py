import pytest
from src.core.profile_matcher import ProfileMatcher

@pytest.fixture
def matcher():
    return ProfileMatcher()

def test_classify_data_engineering(matcher):
    title = "Data Platform & Streaming Engineer (m/w/d)"
    desc = "We build real-time streaming pipelines using Apache Flink and Kafka with Python."
    archetype = matcher.classify_archetype(title, desc)
    assert archetype == "data_engineering"
    info = matcher.get_archetype_info(archetype)
    assert "Flink" in " ".join(info.priority_skills) or "ETL" in " ".join(info.priority_skills)

def test_classify_devsecops(matcher):
    title = "Cloud & DevSecOps Platform Engineer (m/w/d)"
    desc = "Operating Kubernetes clusters, writing Terraform IaC, and monitoring with ELK Stack and Prometheus."
    archetype = matcher.classify_archetype(title, desc)
    assert archetype == "devsecops"
    info = matcher.get_archetype_info(archetype)
    assert info.cv_template == "templates/cv_template_devsecops.tex"

def test_classify_cpp_integration(matcher):
    title = "C++ Softwareentwickler für Embedded Linux (m/w/d)"
    desc = "Entwicklung mit C++, Qt, CMake und CAN Bus Anbindung auf Linux Systemen."
    archetype = matcher.classify_archetype(title, desc)
    assert archetype == "cpp_integration"
    info = matcher.get_archetype_info(archetype)
    assert info.cv_template == "templates/cv_template_cpp.tex"

def test_classify_backend_platform(matcher):
    title = "Python Backend Developer (m/w/d)"
    desc = "Building FastAPI REST APIs, PostgreSQL databases, and microservices."
    archetype = matcher.classify_archetype(title, desc)
    assert archetype == "backend_platform"
    info = matcher.get_archetype_info(archetype)
    assert info.cv_template == "templates/cv_template_backend.tex"


def test_profile_matcher_uses_packaged_taxonomy_without_data_directory(tmp_path, monkeypatch):
    import src.core.profile_matcher as profile_matcher

    monkeypatch.setattr(profile_matcher, "ROOT_DIR", str(tmp_path))
    matcher = ProfileMatcher(taxonomy_data=None)

    assert matcher.taxonomy["role_families"]["data_engineering"]["include_skills"]
    assert matcher.classify_archetype("Data Engineer", "Python and Kafka") == "data_engineering"
