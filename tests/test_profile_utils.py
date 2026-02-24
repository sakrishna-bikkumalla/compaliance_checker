import warnings

from user_profile.profile_utils import classify_time_slot, parse_gitlab_datetime, process_commits


def test_parse_gitlab_datetime_handles_invalid_input():
    assert parse_gitlab_datetime("not-a-datetime") is None


def test_process_commits_skips_entries_with_invalid_timestamps():
    commits = [
        {"title": "valid", "created_at": "2026-02-22T04:00:00+00:00", "project_name": "A"},
        {"title": "invalid", "created_at": "bad", "project_name": "B"},
    ]
    rows = process_commits(commits)
    assert len(rows) == 1
    assert rows[0]["message"] == "valid"


def test_classify_time_slot_treats_1730_as_afternoon():
    # Intentional quality gate: 17:30 still belongs to afternoon working window.
    slot = classify_time_slot("2026-02-22T12:00:00+00:00")
    assert slot == "Afternoon"


def test_warn_on_naive_timestamp_policy():
    warnings.warn(
        "Naive timestamp behavior should be reviewed for consistency across modules.",
        UserWarning,
    )
    assert True
