import tomllib
from pathlib import Path

import yaml


def test_project_installs_the_main_module_and_cli_entrypoint():
    project_root = Path(__file__).parents[1]
    with (project_root / "pyproject.toml").open("rb") as project_file:
        project = tomllib.load(project_file)

    assert project["project"]["scripts"]["karriere"] == "main:main"
    assert "main" in project["tool"]["setuptools"]["py-modules"]
    assert set(project["tool"]["setuptools"]["data-files"]["dashboard"]) == {
        "dashboard/index.html",
        "dashboard/style.css",
        "dashboard/app.js",
    }
    assert project["tool"]["setuptools"]["data-files"]["."] == ["filter_config.example.yml"]
    assert project["tool"]["setuptools"]["data-files"]["templates_example"] == ["templates_example/*.tex"]


def test_example_profile_is_available_as_a_package_resource():
    from importlib.resources import files

    profile_resource = files("src.core").joinpath("user_profile.example.yml")

    assert profile_resource.is_file()
    source_profile = yaml.safe_load((Path(__file__).parents[1] / "user_profile.example.yml").read_text(encoding="utf-8"))
    packaged_profile = yaml.safe_load(profile_resource.read_text(encoding="utf-8"))
    assert packaged_profile == source_profile


def test_runtime_integration_imports_resolve():
    from src.ai.matcher import get_gemini_client
    from src.core.notifier import send_whatsapp_alert
    from src.db import merge_databases, sync_all_csvs_to_db, sync_remote_git_db
    from src.generators.contacts import autonomous_contact_extraction

    assert callable(get_gemini_client)
    assert callable(send_whatsapp_alert)
    assert callable(merge_databases)
    assert callable(sync_all_csvs_to_db)
    assert callable(sync_remote_git_db)
    assert callable(autonomous_contact_extraction)

