-- Migration 010: Job Origin and Pipeline Tracking
-- Adds portal, run_id, and scraped_by_user_id to jobs
-- Adds run_id and pipeline_stage to user_jobs

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS portal TEXT;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scraped_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS run_id INTEGER REFERENCES scraper_runs(id) ON DELETE SET NULL;
ALTER TABLE user_jobs ADD COLUMN IF NOT EXISTS pipeline_stage TEXT DEFAULT 'evaluated';

CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);
CREATE INDEX IF NOT EXISTS idx_jobs_run_id ON jobs(run_id);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_by ON jobs(scraped_by_user_id);
CREATE INDEX IF NOT EXISTS idx_user_jobs_stage ON user_jobs(user_id, pipeline_stage);

-- Backfill portal on jobs from known URL patterns
UPDATE jobs SET portal = 'indeed' WHERE portal IS NULL AND url LIKE '%indeed.%';
UPDATE jobs SET portal = 'linkedin' WHERE portal IS NULL AND (url LIKE '%linkedin.com%' OR url LIKE '%licdn%');
UPDATE jobs SET portal = 'xing' WHERE portal IS NULL AND url LIKE '%xing.com%';
UPDATE jobs SET portal = 'bund' WHERE portal IS NULL AND (url LIKE '%bund.de%' OR url LIKE '%interamt.de%');
UPDATE jobs SET portal = 'ba' WHERE portal IS NULL AND url LIKE '%arbeitsagentur.de%';
UPDATE jobs SET portal = 'personio' WHERE portal IS NULL AND url LIKE '%personio%';
UPDATE jobs SET portal = 'ashby' WHERE portal IS NULL AND url LIKE '%ashbyhq%';
UPDATE jobs SET portal = 'greenhouse' WHERE portal IS NULL AND url LIKE '%greenhouse.io%';
UPDATE jobs SET portal = 'arbeitnow' WHERE portal IS NULL AND url LIKE '%arbeitnow%';

-- Backfill recent Run 12 jobs for User 12
UPDATE jobs 
SET portal = 'indeed', run_id = 12, scraped_by_user_id = 12
WHERE scraped_at >= '2026-11-10 17:00:00' AND (portal IS NULL OR portal = 'indeed');
