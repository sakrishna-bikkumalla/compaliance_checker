import pytest

pydantic = pytest.importorskip("pydantic")

from pydantic import BaseModel, Field, HttpUrl

from gitlab_utils.issues import get_user_issues
from gitlab_utils.merge_requests import get_user_mrs


class MRStatsSchema(BaseModel):
    total: int = Field(ge=0)
    merged: int = Field(ge=0)
    closed: int = Field(ge=0)
    opened: int = Field(ge=0)
    pending: int = Field(ge=0)
    assigned_mrs: int = Field(ge=0)


class IssueStatsSchema(BaseModel):
    total: int = Field(ge=0)
    opened: int = Field(ge=0)
    closed: int = Field(ge=0)
    assigned_issues: int = Field(ge=0)


class MRRowSchema(BaseModel):
    title: str | None = None
    project_id: int | None = None
    web_url: HttpUrl | None = None
    state: str | None = None
    created_at: str | None = None
    role: str


class IssueRowSchema(BaseModel):
    title: str | None = None
    project_id: int | None = None
    web_url: HttpUrl | None = None
    state: str | None = None
    created_at: str | None = None
    role: str


class _Client:
    def __init__(self, payloads):
        self.payloads = payloads

    def _get_paginated(self, endpoint, params=None, per_page=50, max_pages=10):
        _ = (params, per_page, max_pages)
        return list(self.payloads.get(endpoint, []))


def test_mr_rows_and_stats_fit_schema():
    payloads = {
        "/merge_requests": [
            {"id": 1, "title": "MR 1", "project_id": 10, "web_url": "https://gitlab.com/mr1", "state": "opened"},
        ]
    }
    rows, stats = get_user_mrs(_Client(payloads), user_id=42)
    MRStatsSchema.model_validate(stats)
    for row in rows:
        MRRowSchema.model_validate(row)


def test_issue_rows_and_stats_fit_schema():
    payloads = {
        "/issues": [
            {"id": 1, "title": "Issue 1", "project_id": 11, "web_url": "https://gitlab.com/issue1", "state": "closed"},
        ]
    }
    rows, stats = get_user_issues(_Client(payloads), user_id=42)
    IssueStatsSchema.model_validate(stats)
    for row in rows:
        IssueRowSchema.model_validate(row)
