import os
import glob
import yaml

def test_skills_structure():
    skill_dirs = glob.glob(".agents/skills/*/")
    assert len(skill_dirs) > 0, "No skills found in .agents/skills"

    for sdir in skill_dirs:
        skill_md = os.path.join(sdir, "SKILL.md")
        assert os.path.exists(skill_md), f"Missing SKILL.md in {sdir}"

        with open(skill_md, "r", encoding="utf-8") as f:
            content = f.read()

        # Check YAML frontmatter
        assert content.startswith("---"), f"SKILL.md in {sdir} must start with YAML frontmatter ---"
        parts = content.split("---", 2)
        assert len(parts) >= 3, f"SKILL.md in {sdir} must have valid YAML frontmatter closing ---"

        frontmatter = yaml.safe_load(parts[1])
        assert "name" in frontmatter, f"Missing 'name' in frontmatter of {sdir}"
        assert "description" in frontmatter, f"Missing 'description' in frontmatter of {sdir}"


def test_candidate_memory_content():
    """Verify that the candidate-memory skill has the required structural sections.

    Intentionally generic — this repo is public and contains no personal data.
    Candidate details live in user_profile.yml (gitignored).
    """
    memory_skill = ".agents/skills/candidate-memory-and-retention/SKILL.md"
    assert os.path.exists(memory_skill)
    with open(memory_skill, "r", encoding="utf-8") as f:
        text = f.read()

    # Verify required structural sections exist (not personal data)
    assert "experience" in text.lower(), "Skill must document experience section"
    assert "education" in text.lower(), "Skill must document education section"
    assert "skill" in text.lower(), "Skill must document skills section"
    assert "---" in text, "Skill must have YAML frontmatter"
