# Job scoring explained

## Goal
Rank jobs transparently; do not auto-apply.

## Score (100 points)
- Core technical match: 35
- Role-family/title match: 20
- Experience-level fit: 15
- Location/remote fit: 10
- Language fit: 10
- Domain fit: 5
- Eligibility fit: 5

## Core technical match
Award points only for terms present in the configured `user_profile.yml` and supported by candidate evidence. Do not score unverified claims.

## Decision bands
- 75–100: high priority, manual review and tailor CV.
- 55–74: review vacancy requirements and language/eligibility conditions.
- 35–54: low priority; keep only if a strong domain or referral exists.
- Below 35: reject with stored reasons.

## Hard exclusions
Roles in `data/exclusion_rules.yaml` must be rejected or explicitly approved. Seniority labels, clearance/citizenship constraints, unpaid mandatory internships and freelance-only work require special handling.

## Explanation output
Every ranked job must include matched skills, missing requirements, penalties, selected profile, final score, and a recommendation. Example: `82: Python/FastAPI/Linux/Docker/CI matched; Kafka missing; German C1 needs verification.`

## Safety
AI ranking may summarize a job description but cannot silently change the deterministic score, generate fictional candidate evidence, or submit applications.