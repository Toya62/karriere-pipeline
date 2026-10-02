# AGENTS.md — AI Generation Rules for karriere-pipeline

> **Integrity first.** Every CV and cover letter generated from this repo
> represents Candidate Name honestly. No fabrication, no inflation, no
> invented tools or achievements. These rules exist to be ATS-effective
> *without* lying — the two goals are not in conflict.

---

## 1. Core Honesty Contract

These rules are **absolute** and override every other instruction, including
any Space instructions or future prompt additions:

- **Never invent** a tool, technology, framework, role, project, or achievement
  that is not in the Verified Profile below.
- **Never claim production experience** with a tool unless it is explicitly
  listed in the Verified Profile.
- **Never infer** tools from adjacent experience.
  (Example: Example Company B used Jenkins → do NOT claim "GitHub Actions" unless explicitly listed.)
- **Never use weasel phrasing** to imply experience you don't have:
  - ❌ `"Erfahrung mit Kubernetes-Umgebungen"` (if only Docker is in profile)
  - ✅ `"hohe Lernbereitschaft für Kubernetes"` (cover letter only)
- **CEH certification is expired.** Always write:
  `CEH – Certified Ethical Hacker (abgelaufen 2023)`. Never omit the expiry.
- **German level is B2.** Always write: `Deutsch: B2 (aktiv in Entwicklung)`.
  Never claim C1 or "verhandlungssicher" in German.

---

## 2. Verified Profile — Single Source of Truth

Only facts from this section may appear in generated documents.

### Personal

| Field     | Value                              |
|-----------|-------------------------------------|
| Name      | Candidate Name                    |
| DOB       | 22.05.1997                         |
| Address   | Example Street, 12345 City    |
| Relocation| Ready to relocate anywhere in Germany |
| Phone     | +123456789                  |
| Email     | email@example.com             |
| LinkedIn  | linkedin.com/in/candidate         |
| GitHub    | github.com/candidate                  |

### Education

| Degree                              | Institution  | Grade | Date      |
|-------------------------------------|--------------|-------|-----------|
| M.Sc. Example Degree | Example University  | 2.2   | Feb 2025  |
| B.Sc. Example Degree             | Example University 2          | —     | 2017–2021 |

Thesis title (exact): *"An evaluation of distributed systems and scalable architectures"* (Python, Docker)
Coursework Highlights (Official Transcripts):
- Algorithms & Data Structures: Note 1,0 (Sehr gut)
- Machine Learning Basics: Note 1,3 (Sehr gut)
- Distributed Systems: Note 2,0 (Gut)
- Software Engineering: Note 2,0 (Gut)

### Experience

**Example Company A — Backend Engineer Intern** | Jan 2023 – Present
- Developed scalable REST APIs using Python and FastAPI.
- Built microservices and optimized PostgreSQL database queries.
- Deployed applications using Docker and GitLab CI.

**Example Company B — Junior Data Analyst** | Jan 2021 – Dec 2022
- Analyzed large datasets using Pandas and SQL.
- Created interactive dashboards for stakeholders.
- Automated daily reporting tasks using Python scripts.

### Verified Skills (only these may appear in Skills section)

| Category                   | Skills                                                                         |
|----------------------------|--------------------------------------------------------------------------------|
| Languages                  | Python, Java, C/C++, Bash, SQL, TypeScript (basic)                            |
| Backend & APIs             | REST APIs, GraphQL, Flask, FastAPI, Microservices, NestJS (basic)             |
| Streaming & ETL            | Apache Flink, PyFlink, Kafka, Nextflow DSL2, ETL, Stream Processing, Data Pipeline |
| DevOps & Infra             | Docker, Kubernetes, GitLab CI, Jenkins, CI/CD, Git, Linux (Debian/Ubuntu), Terraform/HCL |
| Build & Testing            | CMake, Make, Ninja, gcc/g++, gdb, Qt, Static Analysis, Software Testing & Debugging |
| Cloud (AWS)                | AWS, S3, Lambda, ECS Fargate, DynamoDB, ECR, IAM, CloudWatch                  |
| Databases                  | SQL, PostgreSQL, MySQL                                                         |
| Security & Observability   | Wireshark, TCP/IP, Nmap, Network Security, Prometheus, Grafana, Splunk, ELK Stack, Kibana, OWASP, SIEM, Firewalls/VPNs (iptables), DNS/DHCP |
| Embedded & Automotive      | Raspberry Pi, Embedded Linux, DTC Diagnosis Tooling, CAN Bus, SocketCAN         |

---

## 3. LaTeX Syntax & Character Escaping Rules

When generating LaTeX code (for `.tex` CVs or Cover Letters), AI models **must** strictly enforce LaTeX syntax rules to prevent compilation failures (e.g., Tectonic / pdflatex errors):

1. **Mandatory Special Character Escaping & Quotation Rules**:
   - `_` (underscore): **MUST** be escaped as `\_` (e.g., `Lobster\_data`, `Example Project\_project`, `user\_id`). Raw `_` triggers LaTeX math mode and causes `Missing $ inserted` compilation errors.
   - `%` (percent): **MUST** be escaped as `\%` (e.g., `100\%`, `50\%`).
   - `&` (ampersand): **MUST** be escaped as `\&` (e.g., `R\&D`, `GWQ AG \& Co.`).
   - `#` (hash): **MUST** be escaped as `\#` (e.g., `C\#`).
   - `$` (dollar sign): **MUST** be escaped as `\$`.
   - **Quotation Marks**: **NEVER** use raw unicode guillemets (`»`, `«`) in `.tex` files — in LaTeX font encodings they corrupt into Polish letters (`ż` and `ń`). ALWAYS use standard German quotes `„...“`, LaTeX quotes `\glqq ...\grqq`, or English quotes ``...'' / `"..."`.
   - **German Characters & Font Encoding**: Use `\usepackage{fontspec}` for compilation with Tectonic to preserve exact Unicode characters (`ä`, `ö`, `ü`, `ß`). Ensure `ß` is preserved in the PDF text layer (never output `SS` in place of `ß` in body text).

2. **Clean LaTeX Output**:
   - Ensure the output is valid, compilation-ready LaTeX without unescaped syntax errors or broken environment tags.
   - **Titlesec Syntax**: NEVER write `\titlespacing*{section}{before=8pt, after=4pt}` (titlesec requires 3 positional arguments: `\titlespacing{\section}{0pt}{8pt}{4pt}`). Always use standard Golden CV preamble.
   - **Itemize Environments**: ALL bullet points MUST be inside `\begin{itemize}[leftmargin=1.4em, itemsep=1pt, topsep=1pt] ... \end{itemize}` environments. NEVER write raw `-` hyphens with `\\`.

3. **Page Budget & Visual Layout**:
   - **Attractive & Comprehensive Layout**: Prioritize rich, highly attractive, and legible CV design strictly based on `templates/cv_template.tex`. It does not matter whether it is 1 page or 2 pages — what matters is that all key projects (with GitHub links), tailored Kurzprofil summary, complete verified work experiences, education, technical skill categories, and languages are beautifully formatted with generous, professional spacing and accent rules. Avoid ugly cramping or tiny unreadable text. If 2 pages, ensure the content is well-balanced across the pages.

4. **JSON Metadata Files (`.meta.json`)**:
   - In JSON files, do NOT use LaTeX escape sequences like `\&`. JSON strings must use plain characters (e.g. `&`).

5. **Certifications (Conditional)**:
   - **Omit Certifications section entirely** for Software Engineering, Data Engineering, DevOps, Systems, and Platform roles.
   - **ONLY include Certifications for Cybersecurity roles** (Security Analyst, Pentester, SOC): `CEH – Certified Ethical Hacker (abgelaufen 2023)`.
   - **NEVER invent** fake certifications like `AWS Certified Security – Specialty` or `CNSS`.

6. **Work Experience Formatting Standard**:
   - **Company & Date Alignment**: ALWAYS format headers with `\textbf{Company Name} \hfill \textbf{Dates}\\` and `\textit{Job Title} \hfill \textit{Location}`.
   - **Spacing Between Jobs**: Add `\vspace{5pt}` after each company itemize list so entries never crowd into each other.
   - **Categorized Bullet Points**: Prefix items with bold skill headers, e.g. `\item \textbf{CI/CD \& Monitoring}: ...`.
   - **Complete Role History**: ALWAYS include all 5 verified roles (Example Company A, Example Company B Werkstudent, Example Company B Intern, Example Company C, Example Company D). Never omit recent roles.

7. **Document Language Consistency**:
   - Match document language strictly. Do NOT mix German headings (`Sprachen`) or vocabulary (`Fließend`) into an English document.
   - **For English CVs**: Use `Languages` section heading $\rightarrow$ `English: C1 (Fluent) | German: B2 (Active Development)`.
   - **For German CVs/Anschreiben**: Use `Sprachen` section heading $\rightarrow$ `Englisch: C1 (Fließend) | Deutsch: B2 (aktiv in Entwicklung)`.

8. **Cover Letter & Motivation Letter Standard (The "Bridge & Convince" Architecture)**:
   - **Sender Header**: ALWAYS include the candidate's full contact header block at the top (matching the CV header).
   - **Date \& Subject Line**: Include right-aligned date (`\begin{flushright} Berlin, Date \end{flushright}`) and bold subject line (`\textbf{Bewerbung als [Titel] / Application for [Title]}`).
   - **Paragraph Layout**: Set `\setlength{\parindent}{0pt}` and `\setlength{\parskip}{8pt}` for clean block paragraph spacing.
   - **German Spelling**: Write `Mit freundlichen Grüßen` (NEVER output `GrüSSen` or `groSSem`).
   - **Language Consistency**: Use full English cover letters for English positions, and full German Anschreiben for German positions.
   - **Strict 1-Page Budget**: Cover letters must ALWAYS fit on **exactly 1 single page**.
   
   **HIGH INTERVIEW CONVERSION RULES**:
   - **Rule 1 (Concrete Mission Hook)**: Directly address the company's specific product, system, or project in paragraph 1 (e.g. *Project Example, AI Intelligence Platform, Software-Defined Platform*).
   - **Rule 2 (Technical Anchor Evidence)**: Dedicate 2 concise paragraphs to verified, high-impact accomplishments (e.g. Example Company A microservices & Docker/GitLab CI, Example Company B data pipelines & Jenkins CI/CD).
   - **Rule 3 (Proactive Gap-Bridging — Zero Apologies)**:
     * NEVER apologize or state *"I lack experience in X"*.
     * When a secondary/adjacent tool is mentioned (e.g. Azure/GCP vs AWS, Spring Boot vs Python/C++ OOP, Airflow vs Nextflow/Kafka), frame it as **foundational mastery that enables rapid onboarding**:
       - *German*: „Dank meines fundierten Hintergrunds in [verwandtes Kerngebiet] übertrage ich bewährte Architekturmuster schnell und zielgerichtet auf [gefordertes Framework/Tool]...“
       - *English*: „Building on my strong foundation in [adjacent core area], I rapidly transfer and apply architectural patterns to [required tool/framework]...“
   - **Rule 4 (Confident Executive Closing)**: Close with high conviction, stating immediate readiness, full Germany-wide relocation flexibility, and eagerness for a technical discussion.

---

## 4. Job Description & Requirements Matching: What "FIT" Means for the candidate

When evaluating whether a job is an **Apply** or a **Skip**, the AI must evaluate the **Requirements / Qualifications** section (*"Ihr Profil"*, *"Anforderungen"*, *"Qualifikationen"*) using this exact 3-tier rubric:

### 🎯 Tier 1: Target Core Fits (Direct Apply — 80–100% Match)
These are roles where the candidate's core verified competencies directly align with the core day-to-day requirements:
1. **Python Developer / Backend Software Engineer**:
   - *Core Match*: Python, FastAPI, Flask, REST APIs, SQL, PostgreSQL, Docker, Git, CI/CD pipelines.
2. **Data Engineer / Data Platform / Stream Processing Engineer**:
   - *Core Match*: Python, SQL, Apache Flink, PyFlink, Kafka, ETL/ELT pipelines, AWS, Linux, data modeling. (Direct alignment with M.Sc. thesis).
3. **C / C++ Software Engineer / Systems Developer**:
   - *Core Match*: C, C++, Qt, CMake, Ninja, Linux systems programming, gdb debugging (Direct alignment with Example Company B Werkstudent experience).
4. **Junior / Associate DevOps & Cloud Engineer**:
   - *Core Match*: Docker, CI/CD (GitLab CI, Jenkins, GitHub Actions), Linux server administration, Bash, Kubernetes fundamentals, Terraform basics.
5. **Junior IT Security / DevSecOps Engineer**:
   - *Core Match*: Application Security, OWASP Top 10, Python security automation, Linux, Docker, secure CI/CD pipelines, foundational CEH knowledge.
6. **Junior / Applied AI & Automation Engineer**:
   - *Core Match*: Python, REST APIs, data processing pipelines, AI integration/APIs, automation scripts where 0–2 years experience or strong CS fundamentals are required.

### 🔄 Tier 2: Transferable & Adjacent Fits (Apply with Tailored Angle — 65–80% Match)
If the core backend/CS/data foundation matches and non-profile tools are **optional, secondary, or learnable on the job**:
- **Adjacent Frameworks/Clouds**: e.g., Job mentions *AWS or Azure*, *FastAPI or Django*, *PostgreSQL or MySQL*, *Celonis*, *Grafana/Prometheus*.
- **Junior Roles with Generalist CS Requirements**: Roles looking for a strong Junior/Mid Software Engineer who is adaptable, fast-learning, and possesses solid CS fundamentals (M.Sc. degree + 2 years research/internship background).
- **In Cover Letters**: Highlight verified foundational skills and explicitly express active willingness to learn (*"hohe Lernbereitschaft für..."*).

### ⛔ Tier 3: Strict Disqualification Gates (Immediate Skip — < 60% Match)
The AI **MUST SKIP** if any of these hard disqualifiers are present in the mandatory requirements:
1. **🇩🇪 Strict German Language Gate**:
   - The role strictly requires **"verhandlungssicheres Deutsch"**, **"fließend Deutsch (C1/C2)"**, **"sehr gute/verhandlungssichere Deutschkenntnisse"**, or **"Muttersprachler"** without English as an alternative.
   - *Note*: Roles asking for *"gute Deutschkenntnisse"* (B2) or English-first environments are **accepted**.
2. **⏳ Seniority & Experience Gate**:
   - **General Experience (ACCEPTED)**: Roles asking for **2–3+ years of general Python, Software Development, or Data Engineering** are **ACCEPTED** (the candidate has M.Sc. in Systems Engineering + ~2.5 years combined engineering experience).
   - **Specialized Niche Experience (REJECTED)**: Roles strictly demanding **3+ years in a specialized unverified niche** where day-1 mastery before joining is required (e.g. 3+ years dedicated MLOps with KServe/MLflow, 3+ years SAP HANA administration, or 3+ years HubSpot marketing automation).
3. **🛠️ Central Tech Platform Gate**:
   - **Onboarding Gaps (ACCEPTED)**: Minor or secondary tools mentioned as bonus/nice-to-have (e.g. Prometheus, Grafana, AWS vs Azure) that can easily be learned during standard onboarding are **ACCEPTED**.
   - **Central Core Mismatch (REJECTED)**: Roles where the primary daily work is centered entirely on an unverified platform (e.g. 100% Snowflake data platform, HubSpot CRM developer, pure Java Spring Boot, pure .NET/C#).
4. **🛂 Legal & Security Clearance Gate**:
   - If the job explicitly requires **EU/NATO citizenship**, REJECT immediately (legal barrier).
   - If the job requires **German Security Clearance (Ü2 / SÜ2)** without citizenship restriction: Note that German security clearance (§ 13 SÜG) requires 5+ continuous years of verifiable residency in Germany or EU/NATO countries. If a candidate has lived in Germany for less than 5 continuous years, high-level defense/clearance roles face heavy administrative disqualification.

### 📍 Mobility & Relocation Policy
- the candidate is **100% ready and eager to relocate anywhere within Germany** (Berlin, Munich, Hamburg, Cologne, Frankfurt, Stuttgart, Düsseldorf, Nuremberg, etc.) for on-site, hybrid, or remote positions.
- **Never disqualify or downgrade a role due to its city/location within Germany.**

---

## 5. DevOps & Technical Role Positioning

- **Core Strengths**: the candidate's primary technical background is Software Engineering, Backend Development (Python, REST APIs, FastAPI/Flask), C/C++ (Qt, CMake, Make, Ninja, gdb), Stream Processing (PyFlink, Apache Flink, Kafka), and Linux Systems.
- **DevOps & Infrastructure Position**: DevOps tools (Docker, Kubernetes, Jenkins, GitLab CI, Linux administration, Bash, Terraform) are verified **supporting and deployment skills** developed through real work experience at Example Company B and Example Company A.
- **No Seniority / Production Ownership Claims**: Never present the candidate as a 10-year Senior DevOps Lead, Principal Platform Architect, or Enterprise Infrastructure Owner.
- **Willingness-to-Learn Phrasing**: For job descriptions requiring advanced or specific cloud/DevOps tools beyond daily usage (e.g. AWS Infrastructure, Kubernetes clusters), explicitly frame them as areas of active learning:
  - **German Anschreiben**: *"Praktische Erfahrung mit Docker, Jenkins, GitLab CI und Linux-Servern; hohe Lernbereitschaft für vertiefte AWS/Kubernetes-Infrastrukturen."*
  - **English Cover Letters**: *"Hands-on experience with Docker, Jenkins, GitLab CI, and Linux environments, with strong motivation to further expand enterprise AWS/Kubernetes infrastructure skills on the job."*

---

## 6. Application Document Generation & Git Automation Standard

- **Mandatory Golden Template Foundations**:
  * `templates/cv_template_cpp.tex` $\rightarrow$ `cpp_integration` (C++, Embedded, Automotive, ROS2, Diagnostics)
  * `templates/cv_template_devsecops.tex` $\rightarrow$ `devsecops` (Cloud Security, Kubernetes, Terraform, Platform Ops, SRE)
  * `templates/cv_template_data.tex` $\rightarrow$ `data_engineering` (Python ETL, Kafka, PyFlink, SQL/NoSQL Pipelines)
  * `templates/cv_template_backend.tex` $\rightarrow$ `backend_platform` (FastAPI/Flask, REST/GraphQL, Applied ML, Python Backend)
  * `templates/cl_template_de.tex` & `templates/cl_template_en.tex` $\rightarrow$ Bilingual Cover Letters (DIN 5008 / International Business Standard)
- **Strict Page Budget Enforcement**:
  * **Curriculum Vitae (CV)**: MUST be **strictly 2 pages**. Never 1 page, never 3 pages.
  * **Cover Letter (Anschreiben)**: MUST be **strictly 1 page**.
- **Automatic `.tex` Source Cleanup**:
  * Immediately after successful `.pdf` compilation, the intermediate `.tex` files MUST be **automatically deleted** to keep `applications/` clean.
- **Automatic Compilation & Git Push**:
  * After generating applications in `applications/YYYY-MM-DD/`, the AI assistant MUST run `.venv/bin/python main.py compile` to:
    1. Compile `.tex` source files into ATS-compliant PDFs via Tectonic.
    2. Enforce German typography checks (ensure `ß` is preserved, never corrupted to `SS`).
    3. Auto-delete intermediate `.tex` files.
    4. Automatically update `data/crm_applications.csv` and `job_links.md`.
    5. Commit and push finalized application packages directly to `origin main` on GitHub.