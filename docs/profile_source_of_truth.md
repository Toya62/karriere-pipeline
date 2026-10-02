# Profile source of truth

## Purpose
This repository must generate truthful, current and role-relevant application materials.

## Precedence
1. `user_profile.yml` is the machine-readable candidate profile used by matching and application generation.
2. Verified original documents and employment records override derived CV text.
3. Tailored CVs and cover letters may reorder or select facts, but may not change facts.
4. Job-posting data is not evidence of a candidate skill.

If `user_profile.yml` is absent, the application loads `user_profile.example.yml` and warns that the example is active. The example is intentionally incomplete; application and email generation must not be used until the candidate profile has been populated with verified details. Search preferences and filter settings may have defaults, but they are not evidence of candidate qualifications.

## Mandatory review fields
Before an application is generated or sent, update and verify: email, phone, location, availability, work authorization, German CEFR level, English CEFR level, portfolio links, salary/rate if requested.

## Current evidence basis
The repository template contains no verified candidate history. Users must add only facts supported by their own records to `user_profile.yml`; example content and job-posting requirements are not evidence.

## Prohibited behavior
Do not infer seniority, years of experience, cloud production experience, German level, visa/work authorization, availability, salary, or tools not supported by evidence.

## Change process
Edit `user_profile.yml` first, review the diff, regenerate the selected application artifact, and retain a copy of the source job description and final generated files. Treat AI requests and optional Git/CI synchronization as external data transfers; keep personal artifacts out of public remotes.