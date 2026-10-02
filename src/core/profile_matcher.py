#!/usr/bin/env python3
"""
src/profile_matcher.py — Archetype Classifier & Profile Context Router.

Classifies incoming job postings into one of the 4 target archetypes:
1. data_engineering
2. devsecops
3. cpp_integration
4. backend_platform

Provides targeted profile context and template mappings to Gemini and application compilers.
"""

import os
import sys
import re
import yaml
from dataclasses import dataclass
from typing import Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.core.logger import get_logger
from src.core.taxonomy_defaults import DEFAULT_TARGET_PROFILES, DEFAULT_TAXONOMY

logger = get_logger("profile_matcher")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _load_yaml(rel_path: str) -> dict[str, Any]:
    full_path = os.path.join(ROOT_DIR, rel_path)
    if not os.path.exists(full_path):
        return {}
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Error loading YAML {full_path}: {e}")
        return {}


@dataclass
class TargetArchetype:
    key: str
    headline: str
    target_titles: list[str]
    priority_skills: list[str]
    cv_template: str
    cover_template_de: str
    cover_template_en: str


class ProfileMatcher:
    def __init__(self, taxonomy_data: dict[str, Any] | None = None):
        target_profile_data = _load_yaml("data/target_profiles.yaml")
        self.target_profiles = target_profile_data.get("profiles", DEFAULT_TARGET_PROFILES)
        self.taxonomy = taxonomy_data if taxonomy_data is not None else _load_yaml("data/job_taxonomy.yaml")
        if not self.taxonomy:
            self.taxonomy = DEFAULT_TAXONOMY

    def classify_archetype(self, title: str, description: str = "") -> str:
        """Classify a job posting into one of the 4 archetypes based on title and description keywords."""
        text = f"{title} {description}".lower()
        title_lower = title.lower()

        scores = {
            "data_engineering": 0,
            "devsecops": 0,
            "cpp_integration": 0,
            "backend_platform": 0,
        }

        role_families = self.taxonomy.get("role_families", {})

        for archetype, rules in role_families.items():
            # Title keyword matching (+12 per match)
            for inc_title in rules.get("include_titles", []):
                if inc_title.lower() in title_lower:
                    scores[archetype] += 12

            # Skill keyword matching (+2 per match)
            for skill in rules.get("include_skills", []):
                pattern = r'\b' + re.escape(skill.lower()) + r'\b'
                if re.search(pattern, text):
                    scores[archetype] += 2

        # Special priority boosts
        if re.search(r'\b(flink|pyflink|kafka|etl|elt|data pipeline|data engineer|data platform)\b', title_lower):
            scores["data_engineering"] += 15
        if re.search(r'\b(c\+\+|cmake|qt|embedded linux|can bus)\b', title_lower):
            scores["cpp_integration"] += 15
        if re.search(r'\b(devops|devsecops|cloud engineer|platform engineer|sre|terraform|kubernetes)\b', title_lower):
            scores["devsecops"] += 15
        if re.search(r'\b(backend|python developer|software engineer|api developer)\b', title_lower):
            scores["backend_platform"] += 10

        best = max(scores, key=scores.get)
        if scores[best] == 0:
            return "backend_platform"
        return best

    def get_archetype_info(self, archetype_key: str) -> TargetArchetype:
        """Returns structured details, priority skills, and templates for a given archetype."""
        profile = self.target_profiles.get(archetype_key, {})
        headline = profile.get("headline", archetype_key.replace("_", " ").title())
        titles = profile.get("target_titles", [])
        skills = profile.get("priority_skills", [])

        template_map = {
            "backend_platform": "templates/cv_template_backend.tex",
            "data_engineering": "templates/cv_template_data.tex",
            "cpp_integration": "templates/cv_template_cpp.tex",
            "devsecops": "templates/cv_template_devsecops.tex",
        }
        cv_tmpl = template_map.get(archetype_key, "templates/cv_template.tex")

        return TargetArchetype(
            key=archetype_key,
            headline=headline,
            target_titles=titles,
            priority_skills=skills,
            cv_template=cv_tmpl,
            cover_template_de="templates/cl_template_de.tex",
            cover_template_en="templates/cl_template_en.tex",
        )

    def route_job(self, title: str, description: str = "") -> TargetArchetype:
        """Convenience method: classifies a job and returns its target archetype info."""
        archetype_key = self.classify_archetype(title, description)
        return self.get_archetype_info(archetype_key)


if __name__ == "__main__":
    matcher = ProfileMatcher()
    for title in [
        "Data Platform & Streaming Engineer (m/w/d)",
        "DevSecOps / Cloud Platform Engineer (m/w/d)",
        "C++ Softwareentwickler für Embedded Linux",
        "Python Backend Developer (FastAPI/REST)",
    ]:
        info = matcher.route_job(title)
        print(f"{title} -> Archetype: {info.key.upper()} | Template: {info.cv_template}")
