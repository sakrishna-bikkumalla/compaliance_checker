import concurrent.futures

from gitlab_utils import commits, groups, issues, merge_requests, projects, users


def process_single_user(client, username, since=None, until=None):
    """
    Worker function to process a single user.

    Optional date filters (ISO 8601 UTC strings):
      since — start of date range
      until — end of date range
    """
    username = username.strip()
    result = {"username": username, "status": "Success", "error": None, "data": {}}

    if not username:
        return None

    try:
        # 1. Get User
        user_obj = users.get_user_by_username(client, username)
        if not user_obj:
            result["status"] = "Not Found"
            result["error"] = "User not found"
            return result

        user_id = user_obj["id"]
        result["data"]["user"] = user_obj

        # 2. Projects
        projs = projects.get_user_projects(client, user_id, username)
        result["data"]["projects"] = projs

        # 3. Commits — pass since/until as API-level filters
        all_projs_list = projs["all"]
        all_commits, commit_counts, commit_stats = commits.get_user_commits(
            client, user_obj, all_projs_list, since=since, until=until
        )
        result["data"]["commits"] = all_commits
        result["data"]["commit_stats"] = commit_stats

        # Refine Contributed — only projects with verified commits
        result["data"]["projects"]["contributed"] = [
            p
            for p in projs["contributed"]
            if p["id"] in commit_counts and commit_counts[p["id"]] > 0
        ]

        # 4. Groups
        user_groups = groups.get_user_groups(client, user_id)
        result["data"]["groups"] = user_groups

        # 5. MRs — pass since/until → created_after/created_before
        user_mrs, mr_stats = merge_requests.get_user_mrs(client, user_id, since=since, until=until)
        result["data"]["mrs"] = user_mrs
        result["data"]["mr_stats"] = mr_stats

        # 6. Issues — pass since/until → created_after/created_before
        user_issues, issue_stats = issues.get_user_issues(client, user_id, since=since, until=until)
        result["data"]["issues"] = user_issues
        result["data"]["issue_stats"] = issue_stats

    except Exception as e:
        result["status"] = "Error"
        result["error"] = str(e)

    return result


def process_batch_users(client, usernames, since=None, until=None):
    """
    Parallel processing of multiple users.

    Optional date filters (ISO 8601 UTC strings):
      since — start of date range (forwarded to all API calls)
      until — end of date range (forwarded to all API calls)

    Backward compatible: omitting since/until matches original behaviour.
    """
    results = []
    clean_usernames = [u.strip() for u in usernames if u.strip()]

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_user = {
            executor.submit(process_single_user, client, u, since, until): u
            for u in clean_usernames
        }

        for future in concurrent.futures.as_completed(future_to_user):
            try:
                res = future.result()
                if res:
                    results.append(res)
            except Exception as e:
                u = future_to_user[future]
                results.append({"username": u, "status": "Crash", "error": str(e)})

    return results
