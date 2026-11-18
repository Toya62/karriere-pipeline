# Application Templates

Golden LaTeX templates that **always compile cleanly** with Tectonic (XeLaTeX).  
Use these as the **mandatory base** for every new CV and cover letter.

---

## Files & Archetypes

| File | Purpose / Archetype |
|------|---------------------|
| `cv_template.tex` | General ATS-optimised single-column CV |
| `cv_template_backend.tex` | Backend & platform engineering (FastAPI, REST/GraphQL, Python backend, microservices) |
| `cv_template_cpp.tex` | C++, systems, embedded Linux, automotive & ECU diagnostics |
| `cv_template_data.tex` | Data engineering & real-time streaming (PyFlink, Apache Flink, Kafka, ETL/ELT pipelines) |
| `cv_template_devsecops.tex` | DevSecOps, cloud security, Docker, Kubernetes, Terraform & CI/CD platform ops |
| `cl_template_de.tex` | German DIN 5008 Cover Letter (*Anschreiben*) — strictly 1 page |
| `cl_template_en.tex` | English international business cover letter — strictly 1 page |
| `cl_template.tex` | Golden bilingual base cover letter template |

---

## How to instruct AI to generate a new application

Paste this exact prompt:

```
Generate a CV and cover letter for the following job.
Base the CV strictly on templates/cv_template.tex and
the cover letter on templates/cl_template.tex in the
job-scraper-germany repo.
Replace all <<PLACEHOLDER>> fields with real content.
Do NOT change any \usepackage lines.
Do NOT change the tabular column spec — always use the
L and S column types defined in the template.
Only include skills, tools and experience from the
verified profile in the Space instructions.
Push both files to applications/YYYY-MM-DD/ as
cv_N_company.tex and cl_N_company.tex.

Job description:
<<paste job description here>>
```

---

## Critical LaTeX rules (for AI reference)

### Skills / Languages table — ALWAYS use column types L and S

```latex
% CORRECT
\begin{tabularx}{\linewidth}{@{}LX@{}}   % L = bold 4.2cm column
\begin{tabularx}{\linewidth}{@{}SX@{}}   % S = bold 3.0cm column

% WRONG — causes fatal compile error
\begin{tabularx}{\linewidth}{@{}>{}\bfseries p{4.2cm}X@{}}
```

### Packages — always include \usepackage{array}

The `>{...}` column modifier requires `array`.  
Both templates already include it — never remove it.

### German special characters

```latex
Stra\ss{}e   % Straße
Gr\"u\ss{}en % Grüßen
Ausgew\"ahlte % Ausgewählte
```

### German level — fixed string, no exceptions

```
Deutsch: B2 (aktiv in Entwicklung)    % German CV
German:  B2 (aktiv in Entwicklung)    % English CV
```

### CEH — always mark expired

```
CEH -- Certified Ethical Hacker (abgelaufen 2023)
```

---

## ATS checklist for German market

- [ ] Single-column layout only
- [ ] No tables used for page layout (only for skills rows)
- [ ] No graphics, icons, or coloured text blocks
- [ ] Section titles clearly labelled (Berufserfahrung, Ausbildung, etc.)
- [ ] Dates in consistent format throughout
- [ ] Hyperlinks styled black (ATS ignores link colour)
- [ ] File named descriptively: `cv_N_company.tex`
- [ ] One page for cover letter, max two pages for CV
