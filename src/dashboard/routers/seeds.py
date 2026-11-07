"""
src/dashboard/routers/seeds.py — Real-time ATS Seed Harvester & Prober Router.
Accepts dynamically discovered company slugs and portal URLs from the Sarathi extension
or scraping pipeline, and registers them into active crawler seed files.
"""

import os
import json
from fastapi import APIRouter
from pydantic import BaseModel, Field

from scripts.harvest_ats_slugs import (
    extract_ats_slug_from_url,
    resolve_and_extract_ats_slug,
    append_slug_to_seed,
    PERSONIO_SEED_FILE,
    ASHBY_SEED_FILE,
    GREENHOUSE_SEED_FILE,
    DB_COMPANY_SLUGS_FILE,
)
from src.core.logger import get_logger

logger = get_logger("seeds_router")

router = APIRouter(prefix="/api/seeds", tags=["seeds"])


class DiscoverSeedRequest(BaseModel):
    url: str = Field(default="", description="Target job, redirect, or ATS portal URL")
    ats_type: str = Field(default="", description="Optional ATS platform hint (personio, greenhouse, ashby)")
    slug: str = Field(default="", description="Optional company slug if already parsed")
    company: str = Field(default="", description="Optional human-readable company name")
    source: str = Field(default="extension", description="Discovery source (extension, linkedin, xing, indeed)")


@router.post("/discover")
def discover_and_register_seed(req: DiscoverSeedRequest):
    """
    Discovers, verifies, and appends a new ATS company slug into active crawler seeds.
    Handles direct ATS URLs, uncloaked redirect parameters, and follow-up HTTP redirects.
    """
    ats_type = (req.ats_type or "").strip().lower()
    slug = (req.slug or "").strip().lower()
    final_url = req.url.strip()

    # If slug and ats_type already known (e.g. from client content script)
    if not (ats_type and slug) and final_url:
        res = resolve_and_extract_ats_slug(final_url)
        if res:
            ats_type, slug, final_url = res

    if not ats_type or not slug:
        return {
            "success": False,
            "added": False,
            "reason": "Could not extract valid ATS type and company slug from input",
            "url": req.url,
        }

    was_added = append_slug_to_seed(ats_type, slug)
    logger.info(
        f"[Seed Discovery] Source='{req.source}' ATS='{ats_type}' Slug='{slug}' "
        f"Company='{req.company}' Added={was_added}"
    )

    return {
        "success": True,
        "added": was_added,
        "already_known": not was_added,
        "ats_type": ats_type,
        "slug": slug,
        "company": req.company,
        "final_url": final_url,
        "message": f"Successfully registered '{slug}' to {ats_type.upper()} seed pool"
        if was_added
        else f"Company '{slug}' is already registered in {ats_type.upper()} seeds",
    }


@router.get("")
def list_seed_summary():
    """Returns active seed pool metrics."""
    def count_file(path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return len(json.load(f))
            except Exception:
                pass
        return 0

    return {
        "personio_seeds": count_file(PERSONIO_SEED_FILE),
        "greenhouse_seeds": count_file(GREENHOUSE_SEED_FILE),
        "ashby_seeds": count_file(ASHBY_SEED_FILE),
        "total_db_company_slugs": count_file(DB_COMPANY_SLUGS_FILE),
    }
