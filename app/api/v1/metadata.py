from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


class MetadataResponse(BaseModel):
    team_name: str
    team_members: list[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str


@router.get("/metadata", response_model=MetadataResponse)
async def metadata() -> MetadataResponse:
    s = get_settings()
    return MetadataResponse(
        team_name=s.team_name,
        team_members=s.team_members,
        model=s.model,
        approach=(
            "Trigger-kind-specific prompt templates with grounded fact selection; "
            "Anthropic claude-sonnet-5 at temperature=0; "
            "deterministic fallback when LLM unavailable; "
            "full intent-classification reply router"
        ),
        contact_email=s.contact_email,
        version=s.version,
        submitted_at=s.submitted_at,
    )
