from datetime import datetime, timedelta, timezone

import dateutil.parser


def _parse_commit_time(ts_str: str, ist: timezone):
    """
    Parse a commit timestamp string and return (date_str, time_str, slot, t_obj).

    Handles:
    - Timezone-aware ISO 8601 strings (e.g. "2026-02-22T10:30:00+05:30") — converted directly.
    - Timezone-naive strings (e.g. "2026-02-22T05:00:00") — assumed UTC before conversion.
    - None / empty / unparseable — returns fallback values without raising.

    GitLab commonly uses `committed_date` (primary) or `created_at` (fallback).
    Both are tried in order.
    """
    # Slot boundaries in IST
    morn_start = datetime.strptime("09:30", "%H:%M").time()
    morn_end = datetime.strptime("12:30", "%H:%M").time()
    aft_start = datetime.strptime("14:00", "%H:%M").time()
    aft_end = datetime.strptime("17:00", "%H:%M").time()

    if not ts_str:
        return None, "N/A", "N/A", None

    try:
        dt = dateutil.parser.isoparse(ts_str)
        # If tzinfo is None the GitLab instance returned a naive datetime — assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_ist = dt.astimezone(ist)

        date_str = dt_ist.strftime("%Y-%m-%d")
        time_str = dt_ist.strftime("%I:%M %p")
        t_obj = dt_ist.time()

        if morn_start <= t_obj <= morn_end:
            slot = "Morning"
        elif aft_start <= t_obj <= aft_end:
            slot = "Afternoon"
        else:
            slot = "Other"

        return date_str, time_str, slot, t_obj

    except Exception:
        return ts_str, "N/A", "N/A", None


def get_user_commits(client, user, projects, since=None, until=None):
    """
    Fetches commits for a user across given projects.
    Filters by author name/email because GitLab repository commits API
    does not support author_id reliably.

    Returns:
      - all_commits: List of unique commit dicts
      - project_commit_counts: Dict {project_id: count}
      - stats: Dict {morning_commits, afternoon_commits, total}
    """
    all_commits = []
    project_commit_counts = {}
    seen_shas = set()

    # Use name and email for stricter filtering
    author_name = user.get("name")
    author_email = user.get("email")
    username = user.get("username")

    # Define IST timezone (+5:30)
    ist = timezone(timedelta(hours=5, minutes=30))

    stats = {
        "total": 0,
        "morning_commits": 0,  # 09:30 AM – 12:30 PM IST
        "afternoon_commits": 0,  # 02:00 PM – 05:00 PM IST
    }

    for project in projects:
        try:
            pid = project.get("id")
            pname = project.get("name_with_namespace")

            # Fetch commits — apply date filter at API level when provided
            api_params: dict = {"author": author_name or username, "all": True}
            if since:
                api_params["since"] = since
            if until:
                api_params["until"] = until

            commits_data = client._get_paginated(
                f"/projects/{pid}/repository/commits",
                params=api_params,
                per_page=50,
                max_pages=20,
            )

            if commits_data:
                unique_project_commits = 0
                for c in commits_data:
                    sha = c.get("id")
                    if not sha or sha in seen_shas:
                        continue

                    # Validation — match by name, email, or username
                    c_author_name = c.get("author_name")
                    c_author_email = c.get("author_email")

                    is_match = False
                    if author_name and c_author_name == author_name:
                        is_match = True
                    elif author_email and c_author_email == author_email:
                        is_match = True
                    elif username and (
                        username in str(c_author_name).lower()
                        or username in str(c_author_email).lower()
                    ):
                        is_match = True

                    if not is_match:
                        continue

                    seen_shas.add(sha)
                    unique_project_commits += 1
                    stats["total"] += 1

                    # Parse commit timestamp — try committed_date first, fall back to created_at
                    ts_str = c.get("committed_date") or c.get("created_at")
                    date_str, time_str, slot, _ = _parse_commit_time(ts_str, ist)

                    if slot == "Morning":
                        stats["morning_commits"] += 1
                    elif slot == "Afternoon":
                        stats["afternoon_commits"] += 1

                    all_commits.append(
                        {
                            "project_name": pname,
                            "message": c.get("title"),
                            "date": date_str,
                            "time": time_str,
                            "slot": slot,
                            "author_name": c_author_name,
                            "short_id": c.get("short_id"),
                        }
                    )

                project_commit_counts[pid] = unique_project_commits

        except Exception:
            pass

    return all_commits, project_commit_counts, stats


def get_user_commits_project(client, project_id, username, since=None, until=None):
    """
    Fetches commits for a user from ONE SPECIFIC project.
    Used for project-scoped analytics without discovery.

    Returns:
      - commits_list: List of commit dicts
      - stats: Dict {total, morning_commits, afternoon_commits}
    """
    commits_list = []
    seen_shas: set = set()
    stats = {
        "total": 0,
        "morning_commits": 0,
        "afternoon_commits": 0,
    }

    # Define IST timezone (+5:30)
    ist = timezone(timedelta(hours=5, minutes=30))

    try:
        # Fetch commits — projects/{id}/repository/commits
        api_params: dict = {"author": username, "all": True}
        if since:
            api_params["since"] = since
        if until:
            api_params["until"] = until

        commits_data = client._get_paginated(
            f"/projects/{project_id}/repository/commits",
            params=api_params,
            per_page=50,
            max_pages=20,
        )

        for c in commits_data:
            sha = c.get("id")
            if not sha or sha in seen_shas:
                continue

            # Validate author matches the requested username
            c_author_name = c.get("author_name") or ""
            c_author_email = c.get("author_email") or ""
            uname_lower = username.lower()
            if not (
                uname_lower in c_author_name.lower()
                or uname_lower in c_author_email.lower()
            ):
                continue

            seen_shas.add(sha)
            stats["total"] += 1

            # Parse commit timestamp — try committed_date first, fall back to created_at
            ts_str = c.get("committed_date") or c.get("created_at")
            date_str, time_str, slot, _ = _parse_commit_time(ts_str, ist)

            if slot == "Morning":
                stats["morning_commits"] += 1
            elif slot == "Afternoon":
                stats["afternoon_commits"] += 1

            commits_list.append(
                {
                    "project_id": project_id,
                    "message": c.get("title"),
                    "date": date_str,
                    "time": time_str,
                    "slot": slot,
                    "author_name": c.get("author_name"),
                    "short_id": c.get("short_id"),
                }
            )

    except Exception:
        pass

    return commits_list, stats
