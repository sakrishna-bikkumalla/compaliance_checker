import streamlit as st

from modes.team_leaderboard import (
    _aggregate_team_totals,
    _calculate_score,
    _extract_member_row,
    _team_name_exists,
    _validate_json_teams,
)


def test_calculate_score_formula():
    assert _calculate_score(total_commits=7, merged_mrs=2, issues_closed=3) == 24.5


def test_extract_member_row_for_error_status():
    row = _extract_member_row({"username": "alice", "status": "Error", "error": "timeout"})
    assert row["Username"] == "alice"
    assert row["Score"] == 0
    assert row["Error"] == "timeout"


def test_extract_member_row_for_success_status():
    result = {
        "username": "alice",
        "status": "Success",
        "data": {
            "commit_stats": {"total": 10, "morning_commits": 3, "afternoon_commits": 2},
            "mr_stats": {"total": 4, "merged": 2, "opened": 1, "closed": 1, "assigned_mrs": 2},
            "issue_stats": {"total": 5, "closed": 3, "assigned_issues": 1},
            "groups": [{"name": "grp"}],
        },
    }
    row = _extract_member_row(result)
    assert row["MR Created"] == 4
    assert row["Assigned MRs"] == 2
    assert row["Assigned Issues"] == 1
    assert row["Groups"] == 1
    assert row["Score"] == 27.5


def test_aggregate_team_totals_sums_score_and_metrics():
    rows = [
        {"Total Commits": 4, "MR Merged": 1, "Issues Closed": 2, "Score": 14.0},
        {"Total Commits": 6, "MR Merged": 2, "Issues Closed": 1, "Score": 18.5},
    ]
    totals = _aggregate_team_totals(rows)
    assert totals["Total Commits"] == 10
    assert totals["MR Merged"] == 3
    assert totals["Issues Closed"] == 3
    assert totals["Team Score"] == 32.5


def test_team_name_exists_respects_case_and_exclusion_index():
    st.session_state["teams"] = [{"team_name": "Alpha"}, {"team_name": "Beta"}]
    assert _team_name_exists("alpha")
    assert not _team_name_exists("ALPHA", exclude_index=0)


def test_validate_json_teams_rejects_duplicate_names():
    st.session_state["teams"] = [{"team_name": "Core"}]
    payload = {
        "teams": [
            {
                "team_name": "Core",
                "project_name": "P1",
                "members": [{"name": "A", "username": "alice"}],
            }
        ]
    }
    teams, err = _validate_json_teams(payload)
    assert teams is None
    assert "already exists" in err


def test_validate_json_teams_accepts_valid_payload():
    st.session_state["teams"] = []
    payload = {
        "teams": [
            {
                "team_name": "Platform",
                "project_name": "Compliance",
                "members": [
                    {"name": "Alice", "username": "alice"},
                    {"name": "Bob", "username": "bob"},
                ],
            }
        ]
    }
    teams, err = _validate_json_teams(payload)
    assert err == ""
    assert teams is not None
    assert teams[0]["team_name"] == "Platform"
