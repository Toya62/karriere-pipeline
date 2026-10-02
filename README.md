# Karriere Pipeline 🚀

An automated, local-first job search and application pipeline for the German market. It scrapes job boards, filters and scores listings against your personal profile using AI, presents matches in a local dashboard, and automatically generates tailored LaTeX application documents.

## Why this exists
Searching for jobs in Germany is time-consuming. This tool automates the repetitive parts: finding jobs across 5 platforms, deciding if you match the requirements, and drafting tailored cover letters and CVs that fit the specific job description perfectly.

## Features
- **Multi-Portal Scraping:** Scrapes LinkedIn, Indeed, Bundesagentur für Arbeit, Service.bund.de, and XING.
- **Pure SQLite Architecture:** All scraped jobs, evaluation scores, and CRM tracking records are stored natively in `data/karriere.db`.
- **AI Matching Engine:** Evaluates job descriptions against your profile using Gemini, Groq, or OpenRouter when configured.
- **Automated LaTeX Generation:** Injects your details into beautiful LaTeX templates, creating a highly tailored PDF CV and Cover Letter for every single job.
- **Local-first storage:** SQLite data and generated application files are stored in local repository directories; optional Git/CI workflows can commit and transmit tracked data.
- **Local Dashboard:** Review matches, read generated cover letters, and track your applications at `127.0.0.1:8000` by default.

---

## 🛠️ Getting Started (Important!)

This repository is designed as a generic template. Before you run the pipeline, you **must** configure it with your own data.

### 1. Set Up Your Profile
We use a YAML configuration file to inject your personal data into the AI prompts and LaTeX templates.

```bash
# Copy the example profile to create your own private profile
cp user_profile.example.yml user_profile.yml
```
Open `user_profile.yml` and complete your actual personal details, education, experience, skills, languages, and search preferences. Git ignores this file, but that does not make all pipeline data local-only: AI requests and optional Git synchronization are described below. The example profile is a placeholder and must not be used to generate application materials.

### 2. Set Up Your LaTeX Templates
The AI generates applications using LaTeX templates. We provide clean, generic example templates.

```bash
# Copy the example templates to create your own private templates folder
cp -r templates_example/ templates/
```
Open the `.tex` files in the new `templates/` folder and write your actual work experience and education in the designated sections. **Note: Git ignores the entire `templates/` folder, so your resume history stays private.**

When using an installed `karriere` command outside a source checkout, application templates are read from `./templates` by default. The example `.tex` files are installed under the Python environment prefix's `templates_example/` directory (typically `$VIRTUAL_ENV/templates_example`); copy and customize them before generating applications, or set `KARRIERE_TEMPLATES_DIR` to your writable template directory.

### 3. Install Dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

You must have `tectonic` installed on your machine to compile LaTeX to PDF automatically.
- Mac: `brew install tectonic`
- Linux: `sudo apt install tectonic`

### 4. Configure Environment Variables
Create a `.env` file or export the provider credentials you intend to use:
- `GEMINI_API_KEY`: Enables Gemini matching and application/email generation.
- `GROQ_API_KEY` or `OPENROUTER_API_KEY`: Optional fallback providers for AI job matching. Application and email generation currently use Gemini.
- `LINKEDIN_LI_AT`: Optional (but recommended) for authenticated LinkedIn scraping.

### Privacy and network data flow

This is a local-first tool, not an offline-only or local-only system. AI matching sends job descriptions and relevant candidate-profile context to the configured matching provider (Gemini, Groq, or OpenRouter). Application and email generation send the prompt data they need to Gemini. Review each provider's privacy and retention terms before enabling it, and do not send confidential information.

The database and generated PDFs are local by default, but Git synchronization is used by some dashboard, CLI, and automation flows. Data committed and pushed to a remote repository is transmitted to that Git host and may be visible to anyone with repository access. Keep repositories private when they contain personal/job-search data, review what is tracked before pushing, and do not rely on `.gitignore` as a substitute for checking Git history.

The dashboard CLI binds to `127.0.0.1` by default. Docker Compose publishes the dashboard only on the host loopback interface; the container listens on its internal interface to make that forwarding work. `KARRIERE_GIT_SYNC=false` disables dashboard automatic Git synchronization, and `compile --no-push` prevents the compile command from pushing. These controls do not disable AI-provider requests or all explicit Git operations. `scrape --no-match` skips matching for that scrape run; it is not an offline mode.

---

## 💻 Usage

### 1. Scrape Job Portals
It is highly recommended to run the scraper **locally**. Automated scraping via GitHub Actions is disabled because cloud IPs are instantly blocked by job portals.

```bash
# Scrape all portals for jobs posted in the last 1 day
.venv/bin/python main.py scrape --portal all --days 1

# Scrape only LinkedIn for the last 7 days without triggering AI matching
.venv/bin/python main.py scrape --portal linkedin --days 7 --no-match
```

### 2. View the Dashboard
Start the local dashboard to view your matches, score them, and review the drafted cover letters.

```bash
.venv/bin/python main.py dashboard
```
Open [http://localhost:8000](http://localhost:8000).

### 3. Compile Applications
If you generated new applications, compile the LaTeX source into PDFs:

```bash
.venv/bin/python main.py compile
```
Your compiled PDFs will be saved inside the `.gitignore`d `applications/` folder.

---

## 🐳 Docker (Optional CI/CD)
The Docker workflow publishes an image to GitHub Container Registry when a push to `main` changes `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `requirements.txt`, `pyproject.toml`, `main.py`, files under `src/` or `dashboard/`, or the Docker workflow itself. It can also be run manually. This workflow does not publish an image on every `main` push.

You can pull and run the dashboard image on your local home server or Raspberry Pi:
```bash
docker pull ghcr.io/<your-username>/karriere-pipeline:latest
docker run -p 127.0.0.1:8000:8000 ghcr.io/<your-username>/karriere-pipeline:latest
```

The container image excludes local profile, data, template, and application files. Use Docker Compose or explicit reviewed volume mounts when you want the container to use local data; do not expose the dashboard port publicly without adding suitable authentication and network controls.

---

## Tests

```bash
.venv/bin/python -m pytest -q
```
