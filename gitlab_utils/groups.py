def get_user_groups(client, user_id):
    """
    Fetch all groups the user belongs to.
    Use: GET /groups with params={"membership": "true"}

    User Request: "groups... fake data is coming pls fetch real data... strictly user's groups"
    Removed 'all_available' to prevent fetching public groups the user isn't a member of.
    """
    groups_list = []
    try:
        # endpoint: /groups
        # params: membership=true -> limit to groups user is explicitly a member of
        # min_access_level=10 (Guest) ensures they have some access.
        groups = client._get_paginated(
            "/groups", params={"membership": "true", "min_access_level": 10}, per_page=50, max_pages=10
        )

        # Deduplication check just in case API returns duplicates
        seen_ids = set()

        for g in groups:
            if g["id"] in seen_ids:
                continue
            seen_ids.add(g["id"])

            groups_list.append(
                {"name": g.get("name"), "full_path": g.get("full_path"), "visibility": g.get("visibility")}
            )

    except Exception as e:
        print(f"Error fetching groups: {e}")

    return groups_list
