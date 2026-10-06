"""Dismissal endpoints: list and permanently dismiss jobs."""

import pandas as pd
from fastapi import APIRouter, HTTPException

from src.dashboard.dismissals import add_to_dismissed, load_dismissed_df
from src.dashboard.git_ops import git_sync_async
from src.dashboard.schemas import DismissRequest, SuccessResponse
from src.dashboard.state import CACHE

router = APIRouter(prefix="/api", tags=["dismissals"])


@router.get("/dismissed")
def list_dismissed():
    """Return every job the user has dismissed."""
    try:
        df = load_dismissed_df()
        if df.empty:
            return []
        return df.astype(object).where(pd.notnull(df), None).to_dict(orient='records')
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dismissed", response_model=SuccessResponse)
def dismiss_job(body: DismissRequest):
    """Permanently record a dismissal in SQLite and the JSON sync file."""
    try:
        add_to_dismissed(
            job_url=body.job_url,
            company=body.company,
            position=body.position,
        )
        CACHE["jobs"] = {}
        git_sync_async("feat: crm dismiss job [auto]")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
