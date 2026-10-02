import yaml

from src.core import config


def test_profile_loader_reads_user_profile_path(tmp_path, monkeypatch):
    profile_path = tmp_path / "user_profile.yml"
    profile_path.write_text(
        yaml.safe_dump({"personal_info": {"name": "Test Candidate", "location": "Berlin"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROFILE_YAML_PATH", profile_path)

    profile = config.load_candidate_profile()

    assert profile["personal_info"]["name"] == "Test Candidate"


def test_profile_loader_warns_when_using_example_profile(tmp_path, monkeypatch):
    example_path = tmp_path / "user_profile.example.yml"
    example_path.write_text(
        yaml.safe_dump({"personal_info": {"name": "Example Candidate"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "PROFILE_YAML_PATH", tmp_path / "missing.yml")
    monkeypatch.setattr(config, "EXAMPLE_PROFILE_YAML_PATH", example_path)

    profile = config.load_candidate_profile()

    assert profile["personal_info"]["name"] == "Example Candidate"
