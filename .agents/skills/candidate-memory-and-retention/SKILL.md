---
name: candidate-memory-and-retention
description: Persistent memory and context retention for the candidate profile, verified career history, tailored project mapping, and strict ATS formatting rules. All personal data is loaded from user_profile.yml (gitignored).
---

# Candidate Memory & Profile Knowledge Base

> **Privacy Note**: This skill file contains no personal data. All candidate
> details (name, contact, education, experience) are loaded at runtime from
> `user_profile.yml` which is gitignored and never committed.

## 1. Master Candidate Profile

Personal data is sourced from `user_profile.yml` and `data/candidate_master.yaml` at runtime. Do NOT hardcode any of the following here:
- Full name, date of birth, address, phone, email
- LinkedIn / GitHub URLs
- Specific employer names or institution names

To access profile data in code, always use `src.core.config` constants:
`PERSONAL_NAME`, `PERSONAL_EMAIL`, `PERSONAL_PHONE`, `PERSONAL_LOCATION`,
`PERSONAL_RELOCATION`, `LINKEDIN_URL`, `GITHUB_URL`.

## 2. Education & Certifications

Loaded from `user_profile.yml` → `personal_info` and `certifications` sections.

Key structural rules:
- Degree, institution, grade, and thesis title must match the YAML exactly
- Never fabricate or upgrade certifications
- Expired certifications must always show their expiry year

## 3. Verified Career Experience

Loaded from `data/candidate_master.yaml` → `experience` section.

Structural rules:
- Never invent new bullet points, tools, or achievements
- Never claim production experience with unlisted tools
- Never omit any listed role from generated CVs

## 4. Tailored Project Portfolio

Select the 2 most relevant projects based on the target role archetype:
- **DevOps / Cloud / Platform / Embedded**: hardware pipeline projects + streaming platform
- **Data Engineering / Analytics / Backend / AI**: ETL pipeline projects + streaming platform

## 5. Non-Negotiable Application Standards

- **CV**: Strictly 2 pages (per project rules in AGENTS.md)
- **Cover Letter**: Strictly 1 page
- **Language Alignment**: German documents for German postings; English for English postings
- **LaTeX Safety**: All special characters (`&`, `%`, `$`, `#`, `_`) must be escaped
- **Tracking**: Every compiled application is added to `data/crm_applications.csv` and `job_links.md`
- **Honesty**: Never fabricate tools, roles, or achievements not in `user_profile.yml`
