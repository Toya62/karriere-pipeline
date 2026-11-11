#!/usr/bin/env python3
"""Database migration tool: streams jobs, evaluations, and applications to Supabase."""

import argparse
import os
import sys
import psycopg2
import psycopg2.extras

# Add repo root to import path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.database import get_db_connection


def run_migration(dest_url: str, source_sqlite: str | None = None):
    print("Connecting to Supabase PostgreSQL...")
    dest_conn = psycopg2.connect(dest_url)
    dest_conn.autocommit = False
    dest_cur = dest_conn.cursor()

    # 1. Apply Schema
    schema_path = os.path.join(os.path.dirname(__file__), "supabase_schema.sql")
    if os.path.exists(schema_path):
        print("Applying Supabase schema...")
        with open(schema_path, "r", encoding="utf-8") as f:
            dest_cur.execute(f.read())
        dest_conn.commit()
        print("✓ Supabase schema applied successfully.")

    # 2. Source Connection
    print("Reading from source database...")
    if source_sqlite:
        import sqlite3
        src_conn = sqlite3.connect(source_sqlite)
        src_cur = src_conn.cursor()
    else:
        src_conn = get_db_connection()
        src_cur = src_conn.cursor()

    # 3. Migrate Users
    src_cur.execute("SELECT id, email, hashed_password, full_name, auth_provider, google_id, role, tier FROM users")
    users = src_cur.fetchall()
    print(f"Found {len(users)} users to migrate...")

    user_sql = """
    INSERT INTO public.users (id, email, hashed_password, full_name, auth_provider, google_id, role, tier)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        email = EXCLUDED.email,
        hashed_password = EXCLUDED.hashed_password,
        full_name = EXCLUDED.full_name,
        auth_provider = EXCLUDED.auth_provider,
        google_id = EXCLUDED.google_id,
        role = EXCLUDED.role,
        tier = EXCLUDED.tier
    """
    if users:
        psycopg2.extras.execute_batch(dest_cur, user_sql, users)
        dest_conn.commit()
        dest_cur.execute("SELECT setval(pg_get_serial_sequence('users', 'id'), COALESCE(MAX(id), 1)) FROM users;")
        dest_conn.commit()
        print(f"  Migrated {len(users)} users.")

    # 4. Migrate Jobs
    src_cur.execute("SELECT id, company, title, url, location, description, scraped_at FROM jobs")
    jobs = src_cur.fetchall()
    print(f"Found {len(jobs)} jobs to migrate...")

    job_sql = """
    INSERT INTO public.jobs (id, company, title, url, location, description, scraped_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        company = EXCLUDED.company,
        title = EXCLUDED.title,
        url = EXCLUDED.url,
        location = EXCLUDED.location,
        description = EXCLUDED.description,
        scraped_at = EXCLUDED.scraped_at
    """
    batch_size = 500
    for i in range(0, len(jobs), batch_size):
        batch = jobs[i : i + batch_size]
        psycopg2.extras.execute_batch(dest_cur, job_sql, batch)
        dest_conn.commit()
        print(f"  Migrated jobs {i + len(batch)} / {len(jobs)}")

    # Reset jobs sequence
    dest_cur.execute("SELECT setval(pg_get_serial_sequence('jobs', 'id'), COALESCE(MAX(id), 1)) FROM jobs;")
    dest_conn.commit()

    # 4. Migrate Evaluations
    src_cur.execute("SELECT id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at FROM evaluations")
    evals = src_cur.fetchall()
    print(f"Found {len(evals)} evaluations to migrate...")

    eval_sql = """
    INSERT INTO public.evaluations (id, job_id, status, score, chance, archetype, matched_skills, gaps, summary, evaluated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        status = EXCLUDED.status,
        score = EXCLUDED.score,
        chance = EXCLUDED.chance,
        archetype = EXCLUDED.archetype,
        matched_skills = EXCLUDED.matched_skills,
        gaps = EXCLUDED.gaps,
        summary = EXCLUDED.summary,
        evaluated_at = EXCLUDED.evaluated_at
    """
    for i in range(0, len(evals), batch_size):
        batch = evals[i : i + batch_size]
        psycopg2.extras.execute_batch(dest_cur, eval_sql, batch)
        dest_conn.commit()
        print(f"  Migrated evaluations {i + len(batch)} / {len(evals)}")

    dest_cur.execute("SELECT setval(pg_get_serial_sequence('evaluations', 'id'), COALESCE(MAX(id), 1)) FROM evaluations;")
    dest_conn.commit()

    # 5. Migrate Applications
    src_cur.execute("SELECT id, job_id, cv_pdf_path, cover_pdf_path, status, applied_at, sent_at, sent_method, sent_to, follow_up_at, notes, user_id FROM applications")
    apps = src_cur.fetchall()
    print(f"Found {len(apps)} applications to migrate...")

    app_sql = """
    INSERT INTO public.applications (id, job_id, cv_pdf_path, cover_pdf_path, status, applied_at, sent_at, sent_method, sent_to, follow_up_at, notes, user_id)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE SET
        cv_pdf_path = EXCLUDED.cv_pdf_path,
        cover_pdf_path = EXCLUDED.cover_pdf_path,
        status = EXCLUDED.status,
        applied_at = EXCLUDED.applied_at,
        sent_at = EXCLUDED.sent_at,
        sent_method = EXCLUDED.sent_method,
        sent_to = EXCLUDED.sent_to,
        follow_up_at = EXCLUDED.follow_up_at,
        notes = EXCLUDED.notes,
        user_id = EXCLUDED.user_id
    """
    for i in range(0, len(apps), batch_size):
        batch = apps[i : i + batch_size]
        psycopg2.extras.execute_batch(dest_cur, app_sql, batch)
        dest_conn.commit()
        print(f"  Migrated applications {i + len(batch)} / {len(apps)}")

    dest_cur.execute("SELECT setval(pg_get_serial_sequence('applications', 'id'), COALESCE(MAX(id), 1)) FROM applications;")
    dest_conn.commit()

    dest_conn.close()
    src_conn.close()
    print("\n🎉 Migration to Supabase completed successfully!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate Karriere Pipeline DB to Supabase.")
    parser.add_argument("--dest", required=False, default=os.getenv("SUPABASE_DATABASE_URL") or os.getenv("DATABASE_URL"), help="Supabase PostgreSQL connection URI")
    parser.add_argument("--sqlite", required=False, default=None, help="Path to source SQLite db (optional)")
    args = parser.parse_args()

    if not args.dest:
        print("Error: Missing destination Supabase PostgreSQL URI.")
        print("Provide --dest 'postgresql://postgres.wwcqboekfyivwcxjldwk:[PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres'")
        sys.exit(1)

    run_migration(args.dest, args.sqlite)

