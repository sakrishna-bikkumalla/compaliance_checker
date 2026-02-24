from datetime import timedelta, timezone

from gitlab_utils.commits import _parse_commit_time, get_user_commits
from gitlab_utils.issues import get_user_issues
from gitlab_utils.merge_requests import get_user_mrs


class _Client:
    def __init__(self, payloads):
        self.payloads = payloads

    def _get_paginated(self, endpoint, params=None, per_page=50, max_pages=10):
        _ = (params, per_page, max_pages)
        return list(self.payloads.get(endpoint, []))


def test_parse_commit_time_classifies_morning_slot():
    ist = timezone(timedelta(hours=5, minutes=30))
    date_str, _, slot, _ = _parse_commit_time("2026-02-22T04:15:00+00:00", ist)
    assert date_str == "2026-02-22"
    assert slot == "Morning"


def test_get_user_commits_deduplicates_sha_and_counts_valid_matches():
    user = {"name": "Alice Doe", "email": "alice@example.com", "username": "alice"}
    projects = [{"id": 1, "name_with_namespace": "grp/proj"}]
    payloads = {
        "/projects/1/repository/commits": [
            {
                "id": "sha-1",
                "title": "feat: add endpoint",
                "author_name": "Alice Doe",
                "author_email": "alice@example.com",
                "committed_date": "2026-02-22T04:30:00+00:00",
                "short_id": "sha-1",
            },
            {
                "id": "sha-1",
                "title": "feat: duplicate event",
                "author_name": "Alice Doe",
                "author_email": "alice@example.com",
                "committed_date": "2026-02-22T04:45:00+00:00",
                "short_id": "sha-1",
            },
            {
                "id": "sha-2",
                "title": "chore: other author",
                "author_name": "Bob",
                "author_email": "bob@example.com",
                "committed_date": "2026-02-22T06:00:00+00:00",
                "short_id": "sha-2",
            },
        ]
    }
    commits, commit_counts, stats = get_user_commits(_Client(payloads), user, projects)

    assert len(commits) == 1
    assert commit_counts == {1: 2}
    assert stats["total"] == 1
    assert stats["morning_commits"] == 1


def test_get_user_mrs_tracks_total_states_and_assigned_count():
    payloads = {
        "/merge_requests": [
            {"id": 1, "state": "merged", "title": "MR1", "project_id": 10, "web_url": "u1"},
            {"id": 2, "state": "opened", "title": "MR2", "project_id": 10, "web_url": "u2"},
            {"id": 1, "state": "merged", "title": "MR1", "project_id": 10, "web_url": "u1"},
        ]
    }
    mrs, stats = get_user_mrs(_Client(payloads), user_id=99)

    assert len(mrs) == 2
    assert stats["total"] == 2
    assert stats["merged"] == 1
    assert stats["opened"] == 1
    assert stats["pending"] == 1
    assert stats["assigned_mrs"] == 2


def test_get_user_issues_deduplicates_across_roles():
    payloads = {
        "/issues": [
            {"id": 11, "state": "opened", "title": "I1", "project_id": 5, "web_url": "x"},
            {"id": 12, "state": "closed", "title": "I2", "project_id": 5, "web_url": "y"},
            {"id": 11, "state": "opened", "title": "I1", "project_id": 5, "web_url": "x"},
        ]
    }
    issues, stats = get_user_issues(_Client(payloads), user_id=7)

    assert len(issues) == 2
    assert stats["total"] == 2
    assert stats["opened"] == 1
    assert stats["closed"] == 1
    assert stats["assigned_issues"] == 2


def test_get_user_issues_does_not_count_missing_ids_in_assigned_stats():
    payloads = {
        "/issues": [
            {"id": None, "state": "opened", "title": "bad", "project_id": 1, "web_url": "x"},
        ]
    }
    _, stats = get_user_issues(_Client(payloads), user_id=1)

    # Intentional quality gate: missing IDs should not contribute to assigned_issues.
    assert stats["assigned_issues"] == 0
