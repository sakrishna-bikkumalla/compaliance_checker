import pandas as pd
import streamlit as st

from gitlab_utils import commits, groups, issues, merge_requests, projects


def render_user_profile(client, simple_user_info):
    """
    Renders the User Profile UI.
    """
    if not simple_user_info:
        st.error("User info not provided.")
        return

    user_id = simple_user_info.get("id")
    username = simple_user_info.get("username")
    name = simple_user_info.get("name")
    avatar_url = simple_user_info.get("avatar_url")
    web_url = simple_user_info.get("web_url")

    # Header
    col1, col2 = st.columns([1, 4])
    with col1:
        if avatar_url:
            st.image(avatar_url, width=100)
    with col2:
        st.markdown(f"### {name} (@{username})")
        st.markdown(f"**ID:** {user_id} | [GitLab Profile]({web_url})")

    # Fetch Data
    with st.spinner("Fetching comprehensive user data..."):
        # 1. Projects
        proj_data = projects.get_user_projects(client, user_id, username)

        # 2. Commits - Passing full simple_user_info
        all_projs = proj_data["all"]
        all_commits, commit_counts, commit_stats = commits.get_user_commits(client, simple_user_info, all_projs)

        verified_contributed = []
        for p in proj_data["contributed"]:
            if commit_counts.get(p["id"], 0) > 0:
                verified_contributed.append(p)

        personal_projects = proj_data["personal"]

        # 3. Groups
        user_groups = groups.get_user_groups(client, user_id)

        # 4. MRs
        user_mrs, mr_stats = merge_requests.get_user_mrs(client, user_id)

        # 5. Issues
        user_issues, issue_stats = issues.get_user_issues(client, user_id)

    # --- Display ---

    # Projects
    st.markdown("---")
    st.subheader("📦 Projects")
    p_col1, p_col2 = st.columns(2)
    with p_col1:
        st.metric("Personal Projects", len(personal_projects))
        if personal_projects:
            with st.expander("View Personal Projects"):
                for p in personal_projects:
                    st.write(f"- [{p['name_with_namespace']}]({p['web_url']})")
    with p_col2:
        st.metric("Contributed Projects", len(verified_contributed))
        if verified_contributed:
            with st.expander("View Contributed Projects"):
                for p in verified_contributed:
                    st.write(f"- [{p['name_with_namespace']}]({p['web_url']})")

    # Commits
    st.markdown("---")
    st.subheader("💻 Commits Analysis (IST)")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Commits", commit_stats["total"])
    c2.metric("Morning (9:30-12:30)", commit_stats["morning_commits"])
    c3.metric("Afternoon (2:00-5:00)", commit_stats["afternoon_commits"])

    if all_commits:
        with st.expander("View Recent Commits"):
            # Use pandas for table
            df_commits = pd.DataFrame(all_commits)
            # Display updated columns
            st.dataframe(df_commits[["project_name", "message", "date", "time", "slot"]], width="stretch")

    # Groups
    st.markdown("---")
    st.subheader("👥 Groups")
    if user_groups:
        st.write(f"**Total Groups:** {len(user_groups)}")
        df_groups = pd.DataFrame(user_groups)
        st.dataframe(df_groups, width="stretch")
    else:
        st.info("No groups found.")

    # Merge Requests
    st.markdown("---")
    st.subheader("🔀 Merge Requests")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total MRs", mr_stats["total"])
    m2.metric("Merged", mr_stats["merged"])
    m3.metric("Open/Pending", mr_stats["opened"])
    m4.metric("Closed", mr_stats["closed"])

    if user_mrs:
        with st.expander("View MR Details"):
            df_mrs = pd.DataFrame(user_mrs)
            st.dataframe(df_mrs[["title", "role", "state", "created_at"]], width="stretch")

    # Issues
    st.markdown("---")
    st.subheader("⚠️ Issues")
    i1, i2, i3 = st.columns(3)
    i1.metric("Total Issues", issue_stats["total"])
    i2.metric("Open", issue_stats["opened"])
    i3.metric("Closed", issue_stats["closed"])

    if user_issues:
        with st.expander("View Issue Details"):
            df_issues = pd.DataFrame(user_issues)
            st.dataframe(df_issues[["title", "state", "created_at"]], width="stretch")
