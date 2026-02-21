from datetime import datetime, timedelta, timezone

import dateutil.parser


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

    # Define slot boundary times for comparison
    morn_start = datetime.strptime("09:30", "%H:%M").time()
    morn_end = datetime.strptime("12:30", "%H:%M").time()
    aft_start = datetime.strptime("14:00", "%H:%M").time()
    aft_end = datetime.strptime("17:00", "%H:%M").time()

    stats = {
        "total": 0,
        "morning_commits": 0,  # 09:30 AM – 12:30 PM
        "afternoon_commits": 0,  # 02:00 PM – 05:00 PM
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
                valid_project_commits = 0
                for c in commits_data:
                    sha = c.get("id")

                    # Validation
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

                    valid_project_commits += 1

                    if sha in seen_shas:
                        continue

                    seen_shas.add(sha)
                    stats["total"] += 1

                    # Parse and Convert to IST
                    created_at_str = c.get("created_at")
                    try:
                        dt_utc = dateutil.parser.isoparse(created_at_str)
                        dt_ist = dt_utc.replace(tzinfo=timezone.utc).astimezone(ist)

                        date_str = dt_ist.strftime("%Y-%m-%d")
                        time_str = dt_ist.strftime("%I:%M %p")
                        t_obj = dt_ist.time()

                        slot = "Other"
                        if t_obj >= morn_start and t_obj < morn_end:
                            slot = "Morning"
                            stats["morning_commits"] += 1
                        elif t_obj >= aft_start and t_obj <= aft_end:
                            slot = "Afternoon"
                            stats["afternoon_commits"] += 1

                    except Exception:
                        date_str = created_at_str
                        time_str = "N/A"
                        slot = "N/A"

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

                project_commit_counts[pid] = valid_project_commits

        except Exception:
            pass

    return all_commits, project_commit_counts, stats
