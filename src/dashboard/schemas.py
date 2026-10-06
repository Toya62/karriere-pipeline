"""Pydantic request/response schemas for the dashboard JSON API.

Request models validate inbound payloads that previously arrived as ad-hoc
``dict`` objects. Fields that distinguish "omitted" from "explicitly cleared"
(notably ``notes``) are resolved from :attr:`BaseModel.model_fields_set` by the
routers so the ``UNSET`` sentinel semantics of the CRM layer are preserved.
"""


from pydantic import BaseModel, ConfigDict


class _LenientModel(BaseModel):
    """Base model that tolerates and keeps unknown client fields."""

    model_config = ConfigDict(extra="allow")


class ApplicationUpsertRequest(_LenientModel):
    """Body for ``POST /api/applications``."""

    company: str = ""
    position: str = ""
    job_url: str = ""
    cv_pdf_path: str | None = None
    cover_pdf_path: str | None = None
    notes: str | None = None
    date_applied: str | None = None


class ApplicationPatchRequest(_LenientModel):
    """Body for ``PATCH /api/applications`` and ``/api/applications/notes``."""

    company: str | None = None
    position: str | None = None
    job_url: str | None = None
    notes: str | None = None
    status: str | None = None


class ApplicationDeleteRequest(_LenientModel):
    """Optional body for ``DELETE /api/applications``."""

    cv_pdf_path: str | None = None
    company: str | None = None
    position: str | None = None
    job_url: str | None = None


class DismissRequest(_LenientModel):
    """Body for ``POST /api/dismissed``."""

    job_url: str | None = None
    company: str | None = None
    position: str | None = None


class ScraperRunRequest(_LenientModel):
    """Body for ``POST /api/run-scraper`` and its alias."""

    portal: str = "all"
    days: int | str = 1


class GenerateEmailRequest(_LenientModel):
    """Body for ``POST /api/generate-email``."""

    company: str = ""
    position: str = ""
    description: str = ""
    job_url: str = ""
    email: str = ""


class GenerateApplicationRequest(_LenientModel):
    """Body for ``POST /api/generate-application``."""

    company: str = ""
    position: str = ""
    description: str = ""
    job_url: str = ""
    location: str = ""
    language: str | None = None


class SuccessResponse(BaseModel):
    """Generic ``{"success": true}`` acknowledgement."""

    success: bool = True


class MessageResponse(BaseModel):
    """Generic ``{"success": ..., "message": ...}`` acknowledgement."""

    success: bool = True
    message: str = ""


class ErrorResponse(BaseModel):
    """Generic ``{"error": ...}`` failure body."""

    error: str


class ApprovedIndexEntry(BaseModel):
    """A row of ``GET /api/approved-index``."""

    title: str = ""
    company: str = ""
    job_url: str = ""


class JobRecord(_LenientModel):
    """A row of ``GET /api/jobs`` (one dataset view record).

    Extra columns are preserved so future SQL fields do not break the response
    model; the declared fields mirror the current query projection.
    """

    company: str = ""
    title: str = ""
    job_url: str = ""
    location: str | None = None
    scraped_at: str | None = None
    date_posted: str | None = None
    first_seen: str | None = None
    gemini_status: str | None = None
    score: int = 0
    gemini_score: int = 0
    gemini_interview_chance: str | None = None
    target_archetype: str | None = None
    gemini_matched_skills: str | None = None
    gemini_gaps: str | None = None
    gemini_summary: str | None = None
    evaluated_at: str | None = None
    matched_skills: str | None = None
    ai_score: str | None = None
    ai_reason: str | None = None
    description: str | None = None

