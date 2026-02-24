from unittest.mock import patch

from gitlab_utils import batch


@patch("gitlab_utils.users.get_user_by_username")
@patch("gitlab_utils.projects.get_user_projects")
@patch("gitlab_utils.commits.get_user_commits")
@patch("gitlab_utils.groups.get_user_groups")
@patch("gitlab_utils.merge_requests.get_user_mrs")
@patch("gitlab_utils.issues.get_user_issues")
def test_process_single_user_success_filters_contributed_projects(
    mock_issues,
    mock_mrs,
    mock_groups,
    mock_commits,
    mock_projects,
    mock_users,
):
    username = "alice"
    user_id = 123

    mock_users.return_value = {"id": user_id, "username": username, "name": "Alice Doe"}
    mock_projects.return_value = {
        "personal": [{"id": 1}],
        "contributed": [{"id": 2}, {"id": 3}],
        "all": [{"id": 1}, {"id": 2}, {"id": 3}],
    }
    mock_commits.return_value = ([], {2: 4, 3: 0}, {"total": 4, "morning_commits": 2})
    mock_groups.return_value = [{"name": "core"}]
    mock_mrs.return_value = ([], {"total": 1, "merged": 1, "opened": 0, "closed": 0})
    mock_issues.return_value = ([], {"total": 1, "closed": 1, "opened": 0})

    result = batch.process_single_user(client=object(), username=username)

    assert result["status"] == "Success"
    assert result["data"]["projects"]["contributed"] == [{"id": 2}]
    assert result["data"]["commit_stats"]["total"] == 4
    assert result["data"]["mr_stats"]["merged"] == 1
    assert result["data"]["issue_stats"]["closed"] == 1


@patch("gitlab_utils.users.get_user_by_username", return_value=None)
def test_process_single_user_not_found(mock_user_lookup):
    result = batch.process_single_user(client=object(), username="ghost")

    assert result["status"] == "Not Found"
    assert result["error"] == "User not found"
    mock_user_lookup.assert_called_once()


def test_process_single_user_blank_username_returns_none():
    assert batch.process_single_user(client=object(), username="   ") is None
