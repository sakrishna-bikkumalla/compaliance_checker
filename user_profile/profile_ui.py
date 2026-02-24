import streamlit as st

from user_profile.profile_utils import (
    process_commits,
    process_groups,
    split_projects,
)


def render_user_profile(client, user_info):
    st.subheader(f"User: {user_info['name']} (@{user_info['username']}, ID: {user_info['id']})")
    if user_info.get("avatar_url"):
        st.image(user_info["avatar_url"], width=80)
    st.markdown(f"[View GitLab Profile]({user_info.get('web_url', '')})")

    user_id = user_info["id"]

    try:
        groups = client.users.get_user_groups(user_id)
    except Exception:
        # Keep UI clean even if groups API is unavailable, but log for debug
        # st.warning(f"Debug: Could not load groups: {e}")
        groups = []

    try:
        projects = client.users.get_user_projects(user_id)
    except Exception as e:
        st.warning(f"Could not load projects: {e}")
        projects = []

    try:
        commits_raw = client.users.get_user_commits(user_info)
    except Exception as e:
        st.warning(f"Could not load commits: {e}")
        commits_raw = []

    commit_rows = process_commits(commits_raw)
    group_rows = process_groups(groups)
    try:
        issues_raw = client.users.get_user_issues(user_id)
    except Exception:
        issues_raw = []

    try:
        mrs_raw = client.users.get_user_merge_requests(user_id)
    except Exception:
        mrs_raw = []

    # Simple processing for lists
    issue_rows = [
        {
            "title": i.get("title"),
            "state": i.get("state"),
            "created_at": i.get("created_at"),
            "web_url": i.get("web_url"),
        }
        for i in issues_raw
    ]
    mr_rows = [
        {
            "title": m.get("title"),
            "state": m.get("state"),
            "created_at": m.get("created_at"),
            "web_url": m.get("web_url"),
        }
        for m in mrs_raw
    ]

    st.subheader("📊 Account Statistics")

    personal_projects, contributed_projects = split_projects(projects, user_info)

    proj_count = len(projects)
    group_count = len(group_rows)
    issue_count = len(issue_rows)
    mr_count = len(mr_rows)
    commit_count = len(commit_rows)

    personal_commit_count = len([c for c in commit_rows if (c.get("project_type") or "").lower() == "personal"])
    contributed_commit_count = len([c for c in commit_rows if (c.get("project_type") or "").lower() == "contributed"])
    morning_commits = len([c for c in commit_rows if (c.get("slot") or "").lower() == "morning"])
    afternoon_commits = len([c for c in commit_rows if (c.get("slot") or "").lower() == "afternoon"])

    cards = [
        ("Projects", proj_count),
        ("Groups", group_count),
        ("Issues", issue_count),
        ("Merge Requests", mr_count),
        ("Commits", commit_count),
    ]
    cols = st.columns(5)
    for idx, (label, value) in enumerate(cards):
        with cols[idx]:
            st.metric(label, value)

    st.markdown("---")
    st.subheader("📄 Detailed Report")

    st.markdown("#### Projects")
    if not projects:
        st.info("No projects found.")
    else:
        if personal_projects:
            st.markdown("**Personal Projects**")
            for p in personal_projects:
                st.markdown(f"- [{p.get('name_with_namespace', p.get('name'))}]({p.get('web_url')})")

        if contributed_projects:
            st.markdown("**Contributed Projects**")
            for p in contributed_projects:
                st.markdown(f"- [{p.get('name_with_namespace', p.get('name'))}]({p.get('web_url')})")

    st.markdown("#### Groups")
    if not group_rows:
        st.info("No groups found.")
    else:
        st.dataframe(
            group_rows,
            width="stretch",
            column_config={
                "name": "Group name",
                "path": "Path",
                "visibility": "Visibility",
                "web_url": "Group URL",
            },
        )

    st.markdown("#### Issues")
    if not issue_rows:
        st.info("No issues found.")
    else:
        st.dataframe(issue_rows, width="stretch")

    st.markdown("#### Merge Requests")
    if not mr_rows:
        st.info("No merge requests found.")
    else:
        st.dataframe(mr_rows, width="stretch")

    st.markdown("#### Commits")
    if not commit_rows:
        st.info("No commits found for this user.")
    else:
        st.markdown("**Commit Summary (Requested Slots)**")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Personal commits", personal_commit_count)
        c2.metric("Contributed commits", contributed_commit_count)
        c3.metric("Morning (9-12)", morning_commits)
        c4.metric("Afternoon (2-5)", afternoon_commits)

        st.dataframe(
            commit_rows,
            width="stretch",
            column_config={
                "project_type": "Project type",
                "project": "Project",
                "message": "Commit message",
                "date": "Date",
                "time": "Time",
                "slot": "Time slot",
            },
        )

    # Multi-sheet export for full user dashboard data
    try:
        from io import BytesIO

        import pandas as pd

        export_payload = {
            "Projects": [
                {
                    "name": p.get("name"),
                    "name_with_namespace": p.get("name_with_namespace"),
                    "web_url": p.get("web_url"),
                    "project_type": "Personal" if p in personal_projects else "Contributed",
                }
                for p in projects
            ],
            "Groups": group_rows,
            "Issues": issue_rows,
            "MergeRequests": mr_rows,
            "Commits": commit_rows,
        }

        output = BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            for sheet_name, sheet_rows in export_payload.items():
                pd.DataFrame(sheet_rows or [{"info": "No data"}]).to_excel(
                    writer, index=False, sheet_name=sheet_name[:31]
                )

        st.download_button(
            label="Download Full User Report (Excel)",
            data=output.getvalue(),
            file_name=f"{user_info.get('username', 'user')}_dashboard_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.info(f"Excel export unavailable for full user report: {e}")
