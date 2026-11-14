# Job scoring explained

## Goal
Rank jobs transparently; do not auto-apply.

## Score (0–100)
The deterministic score is computed by `compute_job_score` in
`src/core/filters.py:743`. It is a sum of skill points and freshness
points, minus penalties, clamped to 0–100. It is not a weighted rubric:
there is no location, language, domain, or eligibility component in the
score itself. Those are handled separately, as hard filters in
`apply_filters` (`src/core/filters.py:898`) — for example
`filter_location` rejects listings outside Germany and `filter_language`
enforces the language gate — before scoring runs.

- **Verified skills: +6 per matched skill.** A skill counts only if it is
  in the configured `VERIFIED_SKILLS` list and appears in the job title,
  company name, or description, matched on word boundaries (so `git`
  does not match "Digitalisierung" and `aws` does not match "lawsuit").
  Points are awarded only for terms supported by candidate evidence.
  Do not score unverified claims.
- **Target-role terms: +5 per term in the title.** Terms:
  `software engineer`, `backend`, `linux`, `devops`, `data engineer`,
  `c++`, `python`, `cloud`, `system`, `embedded`, `security`.
- **Date freshness: 10–50 points.** Based on `date_posted`
  (fallback: `first_seen`):
  - posted < 24h ago: 50 points for a just-posted job, falling by 1 per
    hour (floored at 10);
  - posted < 72h ago: 35 points;
  - posted < 168h (7 days) ago: 25 points;
  - older: 15 points;
  - missing or unparseable date: 25 points.
  Freshness is up to half the score, so a fresh posting with few
  matched skills can outrank an older one with more.
- **Senior-title penalty: −30.** Applied when the title contains
  `senior`, `sr.`, `lead`, `principal`, `head of`, `director`,
  `architect`/`architekt`, unless the title also contains `junior`,
  `jr.`, `werkstudent`, `intern`, or `trainee`.
- **High-experience penalty: −25.** Applied when the description demands
  5+ years of experience (for example `5+ years`, `10+ years`,
  `mindestens 5 Jahre`, `minimum 5 years`, `5 Jahre Berufserfahrung`),
  unless a 0–5 / 1–5 year range is also given. Company-history phrases
  such as "seit 10 Jahren" are excluded before matching.

Total: `max(0, min(100, skill_points + freshness_points − penalties))`.

## Where the score is used
`filter_by_score` (`src/core/filters.py:821`) keeps only jobs scoring
≥ 20; `apply_filters` runs it last, after the hard filters, for every
portal the orchestrator scrapes. The score is a pre-filter, not a final
judgement — the AI matcher makes the approve/reject decision.

## Decision bands
The old bands (75–100 / 55–74 / 35–54 / below 35) described a rubric
the code never implemented and are retired. Use the thresholds in the
next section instead.

## Thresholds — which number governs which decision
Three different numbers govern three different decisions. Do not mix them:

- **20 — deterministic pipeline floor.** `compute_job_score` via
  `filter_by_score(df, min_score=20)` in `apply_filters`. A job below 20
  never reaches the AI matcher.
- **65 / 80 — AI matcher tier bands.** In the matcher prompt
  (`src/ai/matcher.py:62-63`): Tier 1 "High Match, 80–100%" and Tier 2
  "Medium Match, 65–80%". These are the AI model's own fit assessment
  and feed its approve/reject verdict (`is_approved`); they are not the
  deterministic score.
- **85 — auto-generate gate.** `generate-approved --min-score`
  (default 85, `main.py:1152`) and the automatic step after `auto`
  (`main.py:845,918`) generate a CV + cover letter only for approved
  jobs whose AI evaluation score (`e.score` in the `evaluations` table)
  is ≥ 85. This is the AI score, not the deterministic score.
- **75 — retired.** The previous version of this document used 75 as a
  "high priority" band. No code ever used 75 as a threshold; do not use it.

## Hard exclusions
Roles in `data/exclusion_rules.yaml` must be rejected or explicitly approved. Seniority labels, clearance/citizenship constraints, unpaid mandatory internships and freelance-only work require special handling.

## Explanation output
Every ranked job must include matched skills, missing requirements, penalties, selected profile, final score, and a recommendation. Example: `82: Python/FastAPI/Linux/Docker/CI matched; Kafka missing; German C1 needs verification.`

## Safety
AI ranking may summarize a job description but cannot silently change the deterministic score, generate fictional candidate evidence, or submit applications.
