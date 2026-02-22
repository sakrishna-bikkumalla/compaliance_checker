def get_user_issues(client, user_id, since=None, until=None):
    """
    Fetch Issues:
    - Authored Issues  (GET /issues?author_id=:id)
    - Assigned Issues  (GET /issues?assignee_id=:id)

    Optional date filters:
      since (str): ISO 8601 UTC datetime — maps to created_after
      until (str): ISO 8601 UTC datetime — maps to created_before

    Returns:
      - issues_list
      - stats: {total, opened, closed, assigned_issues}
    """
    issues_list = []
    seen_ids: set = set()
    assigned_ids: set = set()
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned_issues": 0}

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_and_add(base_params: dict, role_label: str) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated("/issues", params=params, per_page=50, max_pages=10)
            for item in items:
                item_id = item.get("id")

                if role_label == "Assigned":
                    assigned_ids.add(item_id)

                if item_id not in seen_ids:
                    state = item.get("state")
                    issues_list.append(
                        {
                            "title": item.get("title"),
                            "project_id": item.get("project_id"),
                            "web_url": item.get("web_url"),
                            "state": state,
                            "created_at": item.get("created_at"),
                            "role": role_label,
                        }
                    )
                    seen_ids.add(item_id)
                    stats["total"] += 1
                    if state == "opened":
                        stats["opened"] += 1
                    elif state == "closed":
                        stats["closed"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_and_add({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, "Assigned")

    stats["assigned_issues"] = len(assigned_ids)

    return issues_list, stats


def get_user_issues_project(client, project_id, user_id, since=None, until=None):
    """
    Fetch Issues for a SPECIFIC project.
    - Authored Issues  (GET /projects/{pid}/issues?author_id=:id)
    - Assigned Issues  (GET /projects/{pid}/issues?assignee_id=:id)

    Returns:
      - issues_list
      - stats: {total, opened, closed, assigned_issues}
    """
    issues_list = []
    seen_ids: set = set()
    assigned_ids: set = set()
    stats = {"total": 0, "opened": 0, "closed": 0, "assigned_issues": 0}

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_project_issues(base_params: dict, role_label: str) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated(
                f"/projects/{project_id}/issues",
                params=params,
                per_page=50,
                max_pages=10,
            )
            for item in items:
                item_id = item.get("id")

                if role_label == "Assigned":
                    assigned_ids.add(item_id)

                if item_id not in seen_ids:
                    state = item.get("state")
                    issues_list.append(
                        {
                            "title": item.get("title"),
                            "project_id": project_id,
                            "web_url": item.get("web_url"),
                            "state": state,
                            "created_at": item.get("created_at"),
                            "role": role_label,
                        }
                    )
                    seen_ids.add(item_id)
                    stats["total"] += 1
                    if state == "opened":
                        stats["opened"] += 1
                    elif state == "closed":
                        stats["closed"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_project_issues({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned
    fetch_project_issues({"assignee_id": user_id, "scope": "all"}, "Assigned")

    stats["assigned_issues"] = len(assigned_ids)

    return issues_list, stats
