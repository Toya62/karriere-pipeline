-- ==============================================================================
-- Supabase Schema & Row-Level Security (RLS) for Karriere Pipeline SaaS
-- Project Ref: wwcqboekfyivwcxjldwk
-- ==============================================================================

-- 1. JOBS TABLE (Global Intelligence Pool)
CREATE TABLE IF NOT EXISTS public.jobs (
    id SERIAL PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    location TEXT,
    description TEXT,
    scraped_at TEXT,
    CONSTRAINT unq_jobs_url_company_title UNIQUE (url, company, title)
);

-- 2. EVALUATIONS TABLE
CREATE TABLE IF NOT EXISTS public.evaluations (
    id SERIAL PRIMARY KEY,
    job_id INTEGER UNIQUE REFERENCES public.jobs(id) ON DELETE CASCADE,
    status TEXT,
    score INTEGER,
    chance TEXT,
    archetype TEXT,
    matched_skills TEXT,
    gaps TEXT,
    summary TEXT,
    evaluated_at TEXT
);

-- 3. USERS TABLE (Linked to Supabase auth.users or internal identities)
CREATE TABLE IF NOT EXISTS public.users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    hashed_password TEXT,
    full_name TEXT DEFAULT '',
    auth_provider TEXT DEFAULT 'email',
    google_id TEXT UNIQUE,
    role TEXT DEFAULT 'candidate',
    tier TEXT DEFAULT 'free',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. APPLICATIONS TABLE (Tenant-Isolated)
CREATE TABLE IF NOT EXISTS public.applications (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE DEFAULT 1,
    job_id INTEGER UNIQUE REFERENCES public.jobs(id) ON DELETE CASCADE,
    cv_pdf_path TEXT,
    cover_pdf_path TEXT,
    status TEXT DEFAULT 'Prepared',
    applied_at TEXT,
    sent_at TEXT,
    sent_method TEXT,
    sent_to TEXT,
    follow_up_at TEXT,
    notes TEXT
);

-- 5. SENT EMAILS AUDIT LOG
CREATE TABLE IF NOT EXISTS public.sent_emails (
    id SERIAL PRIMARY KEY,
    application_id INTEGER REFERENCES public.applications(id) ON DELETE CASCADE,
    recipient TEXT NOT NULL,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT DEFAULT 'SENT'
);

-- 6. CANDIDATE PROFILES (Tenant-Isolated Profile Vault)
CREATE TABLE IF NOT EXISTS public.candidate_profiles (
    id SERIAL PRIMARY KEY,
    user_id INTEGER UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    profile_json TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. USER DOCUMENTS (Cloudflare R2 Object Metadata)
CREATE TABLE IF NOT EXISTS public.user_documents (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    filename TEXT NOT NULL,
    r2_key TEXT,
    file_size INTEGER DEFAULT 0,
    content_type TEXT DEFAULT 'application/pdf',
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unq_user_document UNIQUE(user_id, category)
);

-- 8. USER LEARNED AUTOFILL FIELDS
CREATE TABLE IF NOT EXISTS public.user_learned_fields (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES public.users(id) ON DELETE CASCADE,
    field_key TEXT NOT NULL,
    field_value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unq_user_learned_field UNIQUE(user_id, field_key)
);

-- 9. USER JOBS & EVALUATIONS (Tenant-Isolated Evaluation Inbox)
CREATE TABLE IF NOT EXISTS public.user_jobs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    job_id INTEGER NOT NULL REFERENCES public.jobs(id) ON DELETE CASCADE,
    status TEXT,
    score INTEGER,
    chance TEXT,
    archetype TEXT,
    matched_skills TEXT,
    gaps TEXT,
    summary TEXT,
    evaluated_at TEXT,
    is_bookmarked INTEGER DEFAULT 0,
    is_hidden INTEGER DEFAULT 0,
    notes TEXT,
    CONSTRAINT unq_user_job UNIQUE(user_id, job_id)
);

-- ==============================================================================
-- INDEXES
-- ==============================================================================
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON public.jobs(scraped_at);
CREATE INDEX IF NOT EXISTS idx_jobs_url ON public.jobs(url);
CREATE INDEX IF NOT EXISTS idx_evaluations_job_status ON public.evaluations(job_id, status);
CREATE INDEX IF NOT EXISTS idx_evaluations_status ON public.evaluations(status);
CREATE INDEX IF NOT EXISTS idx_evaluations_status_score ON public.evaluations(status, score);
CREATE INDEX IF NOT EXISTS idx_applications_job_status ON public.applications(job_id, status);
CREATE INDEX IF NOT EXISTS idx_applications_follow_up ON public.applications(follow_up_at);
CREATE INDEX IF NOT EXISTS idx_applications_user_id ON public.applications(user_id);
CREATE INDEX IF NOT EXISTS idx_user_jobs_user_status ON public.user_jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_user_jobs_user_score ON public.user_jobs(user_id, score);
CREATE INDEX IF NOT EXISTS idx_user_jobs_job_id ON public.user_jobs(job_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON public.users(email);
CREATE INDEX IF NOT EXISTS idx_user_documents_user ON public.user_documents(user_id);
CREATE INDEX IF NOT EXISTS idx_user_learned_fields_user ON public.user_learned_fields(user_id);

-- ==============================================================================
-- DEFAULT SEED RECORD
-- ==============================================================================
INSERT INTO public.users (email, full_name, role, tier)
VALUES ('candidate@karriere.local', 'Default Candidate', 'candidate', 'pro')
ON CONFLICT (email) DO NOTHING;

