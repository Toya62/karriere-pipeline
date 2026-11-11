"""Script to transfer Toyanath's locked profile and filter config to admin account (user_id = 1).

Consolidates user_profile.yml, filter_config.yml, and data/candidate_master.yaml
into candidate_profiles table in local SQLite and remote PostgreSQL.
"""

import json
import os
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import get_db_connection, save_user_profile, save_user_filter_rules


def build_admin_profile_and_rules():
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # 1. Load user_profile.yml
    up_path = os.path.join(root_dir, "user_profile.yml")
    up = {}
    if os.path.exists(up_path):
        with open(up_path, "r", encoding="utf-8") as f:
            up = yaml.safe_load(f) or {}

    # 2. Load filter_config.yml
    fc_path = os.path.join(root_dir, "filter_config.yml")
    if not os.path.exists(fc_path):
        fc_path = os.path.join(root_dir, "filter_config.example.yml")
    fc = {}
    if os.path.exists(fc_path):
        with open(fc_path, "r", encoding="utf-8") as f:
            fc = yaml.safe_load(f) or {}

    # 3. Load candidate_master.yaml
    cm_path = os.path.join(root_dir, "data", "candidate_master.yaml")
    cm = {}
    if os.path.exists(cm_path):
        with open(cm_path, "r", encoding="utf-8") as f:
            cm = yaml.safe_load(f) or {}

    # Construct verified education
    education = up.get("education") or []
    if cm.get("education"):
        education = cm.get("education")

    # Construct verified experience
    experience = up.get("experience") or []
    if not experience and cm.get("experience"):
        experience = cm.get("experience")

    # Target titles
    target_titles = [
        "Python Developer",
        "Data Engineer",
        "Backend Developer",
        "C++ Developer",
        "Software Engineer",
        "Junior Data Engineer",
        "Analytics Engineer",
        "C++ Software Engineer",
        "Embedded Software Engineer",
        "DevSecOps Engineer",
        "Cloud Automation Engineer",
        "Stream Processing Engineer",
    ]

    # Inclusion keywords
    inclusion_keywords = [
        "Python", "FastAPI", "Flask", "SQL", "Flink", "PyFlink", "Kafka",
        "Docker", "Git", "C++", "Linux", "Kubernetes", "ETL", "Stream Processing",
        "AWS", "PostgreSQL", "SocketCAN", "CMake", "Jenkins", "GitLab CI",
        "Wireshark", "OWASP", "Raspberry Pi", "Splunk", "Bash", "REST API"
    ]

    # Exclusion keywords
    exclusion_keywords = [
        "SAP", "ABAP", "S/4HANA", "PHP", "WordPress", "DotNet", "C#",
        "Spring Boot", "React", "Angular", "Buchhalter", "Dachdecker",
        "Maler", "Bauleiter", "Call Center", "Zeitarbeit", "Arbeitnehmerüberlassung", "Leiharbeit"
    ]

    filter_rules = {
        "discipline": "Software, Systems & Data Engineering",
        "target_titles": target_titles,
        "inclusion_keywords": inclusion_keywords,
        "exclusion_keywords": exclusion_keywords,
        "seniority_level": "Junior/Mid",
        "min_years_experience": 0,
        "max_years_experience": 3,
        "summary": "Toyanath Pandey — M.Sc. Computer & Systems Engineering, TU Ilmenau. Verified PyFlink stream processing, Python/C++ backend systems, AWS cloud pipelines, automotive diagnostics (Bosch), and security analysis.",
        "filter_config": fc,
    }

    profile_dict = {
        "personal_info": up.get("personal_info") or {
            "name": "Toyanath Pandey",
            "email": "pandeytoya22@gmail.com",
            "phone": "+49 159 063 77419",
            "location": "Kerckhoff Str. 146, 45144 Essen",
            "relocation": "Ready to relocate anywhere in Germany",
            "linkedin": "https://linkedin.com/in/pandeytoya",
            "github": "https://github.com/Toya62",
        },
        "education": education,
        "experience": experience,
        "skills": up.get("skills") or {},
        "languages": up.get("languages") or {"English": "C1 (Fluent)", "German": "B2 (aktiv in Entwicklung)"},
        "projects": up.get("projects") or [],
        "experience_summary": up.get("experience_summary") or "",
        "job_search_preferences": up.get("job_search_preferences") or {},
        "ai_rules": up.get("ai_rules") or [],
        "archetype": "systems_engineering",
        "target_titles": target_titles,
        "filter_rules": filter_rules,
        "filter_config": fc,
    }

    return profile_dict, filter_rules


def sync_local():
    profile_dict, filter_rules = build_admin_profile_and_rules()
    print("--> Updating local SQLite data/karriere.db for user_id = 1...")
    save_user_profile(1, profile_dict)
    save_user_filter_rules(1, filter_rules)
    print("✓ Local SQLite updated successfully.")


def sync_remote():
    import subprocess
    profile_dict, filter_rules = build_admin_profile_and_rules()
    profile_json = json.dumps(profile_dict, ensure_ascii=False)
    filter_json = json.dumps(filter_rules, ensure_ascii=False)

    print("--> Updating remote PostgreSQL on Oracle server for user_id = 1...")
    remote_script = f"""import os, psycopg2, json

url = os.getenv('DATABASE_URL')
conn = psycopg2.connect(url)
cur = conn.cursor()

cur.execute("SELECT id FROM users WHERE role = 'admin' OR id = 1 LIMIT 1")
row = cur.fetchone()
if not row:
    cur.execute("INSERT INTO users (email, full_name, role, tier) VALUES ('pandeytoya22@gmail.com', 'Toyanath Pandey', 'admin', 'pro') RETURNING id")
    admin_id = cur.fetchone()[0]
else:
    admin_id = row[0]

prof_json = {json.dumps(profile_json)}
filt_json = {json.dumps(filter_json)}

cur.execute("SELECT id FROM candidate_profiles WHERE user_id = %s", (admin_id,))
if cur.fetchone():
    cur.execute(
        "UPDATE candidate_profiles SET profile_json = %s, filter_rules = %s, updated_at = CURRENT_TIMESTAMP WHERE user_id = %s",
        (prof_json, filt_json, admin_id)
    )
else:
    cur.execute(
        "INSERT INTO candidate_profiles (user_id, profile_json, filter_rules) VALUES (%s, %s, %s)",
        (admin_id, prof_json, filt_json)
    )

conn.commit()
conn.close()
print("✓ Remote PostgreSQL user", admin_id, "updated successfully.")
"""
    cmd = ["ssh", "oracle-server", "docker exec -i karriere-dashboard python -"]
    res = subprocess.run(cmd, input=remote_script, capture_output=True, text=True)
    if res.returncode != 0:
        print("Remote error:", res.stderr)
        raise RuntimeError("Failed to update remote PostgreSQL")
    print(res.stdout.strip())


if __name__ == "__main__":
    sync_local()
    sync_remote()
    print("✓ Admin profile and filter rules synchronization complete.")
