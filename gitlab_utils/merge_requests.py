def get_user_mrs(client, user_id, since=None, until=None):
    """
    Fetch Merge Requests:
    - Authored MRs (GET /merge_requests?author_id=:id)
    - Assigned MRs (GET /merge_requests?assignee_id=:id)

    Optional date filters:
      since (str): ISO 8601 UTC datetime — maps to created_after
      until (str): ISO 8601 UTC datetime — maps to created_before

    Returns:
      - mrs_list: List of MR dicts
      - stats: Dict {total, merged, closed, opened, pending, assigned_mrs}
    """
    mrs_list = []
    seen_ids = set()
    assigned_ids: set = set()  # track MRs where user is assignee (deduplicated)

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0,
        "pending": 0,
        "assigned_mrs": 0,
    }

    # Build optional date filter fragment added to every request
    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_and_add(base_params: dict, role_label: str) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated(
                "/merge_requests", params=params, per_page=50, max_pages=10
            )
            for item in items:
                item_id = item["id"]

                # Track assigned IDs separately (before dedup check)
                if role_label == "Assigned":
                    assigned_ids.add(item_id)

                if item_id not in seen_ids:
                    state = item.get("state")

                    mrs_list.append(
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
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_and_add({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned (tracked separately; deduplication applies to combined mrs_list only)
    fetch_and_add({"assignee_id": user_id, "scope": "all"}, "Assigned")

    stats["assigned_mrs"] = len(assigned_ids)

    return mrs_list, stats


def get_user_mrs_project(client, project_id, user_id, since=None, until=None):
    """
    Fetch Merge Requests for a SPECIFIC project.
    - Authored MRs  (GET /projects/{pid}/merge_requests?author_id=:id)
    - Assigned MRs  (GET /projects/{pid}/merge_requests?assignee_id=:id)

    Returns:
      - mrs_list: List of MR dicts
      - stats: Dict {total, merged, closed, opened, pending, assigned_mrs}
    """
    mrs_list = []
    seen_ids: set = set()
    assigned_ids: set = set()

    stats = {
        "total": 0,
        "merged": 0,
        "closed": 0,
        "opened": 0,
        "pending": 0,
        "assigned_mrs": 0,
    }

    date_params: dict = {}
    if since:
        date_params["created_after"] = since
    if until:
        date_params["created_before"] = until

    def fetch_project_mrs(base_params: dict, role_label: str) -> None:
        try:
            params = {**base_params, **date_params}
            items = client._get_paginated(
                f"/projects/{project_id}/merge_requests",
                params=params,
                per_page=50,
                max_pages=10,
            )
            for item in items:
                item_id = item["id"]

                if role_label == "Assigned":
                    assigned_ids.add(item_id)

                if item_id not in seen_ids:
                    state = item.get("state")
                    mrs_list.append(
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
                    if state == "merged":
                        stats["merged"] += 1
                    elif state == "closed":
                        stats["closed"] += 1
                    elif state == "opened":
                        stats["opened"] += 1
                        stats["pending"] += 1

        except Exception:
            pass

    # 1. Authored
    fetch_project_mrs({"author_id": user_id, "scope": "all"}, "Authored")

    # 2. Assigned (deduplicated against authored)
    fetch_project_mrs({"assignee_id": user_id, "scope": "all"}, "Assigned")

    stats["assigned_mrs"] = len(assigned_ids)

    return mrs_list, stats
