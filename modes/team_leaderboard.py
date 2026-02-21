"""
Team Leaderboard Mode — Dynamic Team Creation + Edit
------------------------------------------------------
Supports creating and editing teams via UI with full session state persistence.
Fetches analytics via process_batch_users() and renders a ranked leaderboard.

Score formula:
    score = (total_commits * 1) + (merged_mrs * 5) + (total_mrs * 2) + (issues_closed * 3)

Session state keys (all prefixed _lb_ except "teams" and "edit_team_index"):
    "teams"                   — master list of saved team dicts
    "edit_team_index"         — int index of team being edited, or None
    "_lb_show_create_form"    — bool, whether create-form is expanded
    "_lb_draft_members"       — member list being built before first Save
    "_lb_edit_draft"          — copy of team being edited (name, project, members)
    "_lb_triggered"           — bool, whether Run Analysis has been clicked
"""

import copy
import datetime
import io

import pandas as pd
import streamlit as st

from gitlab_utils.batch import process_batch_users

# ---------------------------------------------------------------------------
# Session State Bootstrap
# ---------------------------------------------------------------------------


def _init_state() -> None:
    """Initialise all session-state keys used by this module. Safe to call repeatedly."""
    defaults: dict = {
        "teams": [],
        "edit_team_index": None,
        "_lb_show_create_form": False,
        "_lb_show_upload_form": False,
        "_lb_draft_members": [],
        "_lb_edit_draft": {},
        "_lb_triggered": False,
        "_lb_date_since": None,  # ISO 8601 UTC string or None
        "_lb_date_until": None,  # ISO 8601 UTC string or None
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


# ---------------------------------------------------------------------------
# Pure Logic Helpers
# ---------------------------------------------------------------------------


def _render_date_filter() -> tuple[str | None, str | None]:
    """
    Render the date range filter UI.
    Returns (since_iso, until_iso) — both are ISO 8601 UTC strings or None.
    Shows an active filter badge; provides a Clear Filter button.
    """
    import datetime as _dt

    st.markdown("### 📅 Date Range Filter")
    col_from, col_to, col_clear = st.columns([2, 2, 1])

    with col_from:
        from_date = st.date_input(
            "From Date",
            value=None,
            key="_lb_from_date",
            help="Leave blank to fetch full history",
        )
    with col_to:
        to_date = st.date_input(
            "To Date",
            value=None,
            key="_lb_to_date",
            help="Leave blank to fetch full history",
        )
    with col_clear:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("✖ Clear Filter", key="_lb_clear_dates"):
            st.session_state["_lb_date_since"] = None
            st.session_state["_lb_date_until"] = None
            st.session_state["_lb_triggered"] = False
            st.rerun()

    since_iso: str | None = None
    until_iso: str | None = None

    if from_date and to_date:
        if from_date > to_date:
            st.warning("⚠️  **From Date** must be before or equal to **To Date**.")
        else:
            # Convert to UTC ISO 8601 covering the full calendar days
            utc = _dt.timezone.utc
            since_iso = _dt.datetime.combine(from_date, _dt.time.min, tzinfo=utc).isoformat()
            until_iso = _dt.datetime.combine(to_date, _dt.time.max, tzinfo=utc).isoformat()

            st.info(
                f"🗓 Filtering from **{from_date}** to **{to_date}** (UTC).  "
                "Commits, MRs and Issues will be scoped to this range."
            )
    elif from_date or to_date:
        st.warning("Select both **From Date** and **To Date** to apply a filter.")
    else:
        st.caption("No date filter applied — showing full history.")

    # Persist to session_state so it survives reruns
    st.session_state["_lb_date_since"] = since_iso
    st.session_state["_lb_date_until"] = until_iso

    st.divider()
    return since_iso, until_iso


def _calculate_score(
    total_commits: int, merged_mrs: int, total_mrs: int, issues_closed: int
) -> int:
    """Return individual productivity score."""
    return total_commits * 1 + merged_mrs * 5 + total_mrs * 2 + issues_closed * 3


def _extract_member_row(result: dict) -> dict:
    """Flatten one process_batch_users() result into display metrics. Handles errors gracefully."""
    username = result.get("username", "unknown")
    status = result.get("status", "Error")

    if status != "Success":
        return {
            "Username": username,
            "Status": status,
            "Total Commits": 0,
            "Morning Commits": 0,
            "Afternoon Commits": 0,
            "MR Created": 0,
            "MR Merged": 0,
            "MR Open": 0,
            "MR Closed": 0,
            "Issues Raised": 0,
            "Issues Closed": 0,
            "Groups": 0,
            "Score": 0,
            "Error": result.get("error", "Unknown error"),
        }

    data = result.get("data", {})
    c = data.get("commit_stats", {})
    m = data.get("mr_stats", {})
    i = data.get("issue_stats", {})

    total_commits = c.get("total", 0)
    total_mrs = m.get("total", 0)
    merged_mrs = m.get("merged", 0)
    issues_closed = i.get("closed", 0)

    return {
        "Username": username,
        "Status": status,
        "Total Commits": total_commits,
        "Morning Commits": c.get("morning_commits", 0),
        "Afternoon Commits": c.get("afternoon_commits", 0),
        "MR Created": total_mrs,
        "MR Merged": merged_mrs,
        "MR Open": m.get("opened", 0),
        "MR Closed": m.get("closed", 0),
        "Issues Raised": i.get("total", 0),
        "Issues Closed": issues_closed,
        "Groups": len(data.get("groups", [])),
        "Score": _calculate_score(total_commits, merged_mrs, total_mrs, issues_closed),
    }


def _aggregate_team_totals(member_rows: list[dict]) -> dict:
    """Sum numeric metric columns across all member rows."""
    totals: dict = {
        "Total Commits": 0,
        "Morning Commits": 0,
        "Afternoon Commits": 0,
        "MR Created": 0,
        "MR Merged": 0,
        "MR Open": 0,
        "MR Closed": 0,
        "Issues Raised": 0,
        "Issues Closed": 0,
        "Team Score": 0,
    }
    for row in member_rows:
        for key in totals:
            src = "Score" if key == "Team Score" else key
            totals[key] += row.get(src, 0)
    return totals


def _team_name_exists(name: str, exclude_index: int | None = None) -> bool:
    """Return True if a team with this name already exists (optionally skipping one index)."""
    for idx, t in enumerate(st.session_state["teams"]):
        if idx == exclude_index:
            continue
        if t["team_name"].strip().lower() == name.strip().lower():
            return True
    return False


def _build_excel_export(team_data: dict) -> bytes:
    """Multi-sheet Excel: Sheet 1 = leaderboard, Sheet N = per-team member details."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        lb_rows = [
            {"Team": tn, "Project": meta.get("project_name", ""), **totals}
            for tn, (meta, _, totals) in team_data.items()
        ]
        (
            pd.DataFrame(lb_rows)
            .sort_values("Team Score", ascending=False)
            .to_excel(writer, index=False, sheet_name="Leaderboard")
        )
        for team_name, (_, member_rows, _) in team_data.items():
            pd.DataFrame(member_rows).to_excel(writer, index=False, sheet_name=team_name[:31])
    return output.getvalue()


# ---------------------------------------------------------------------------
# UI: JSON Bulk Upload
# ---------------------------------------------------------------------------


def _validate_json_teams(raw: dict) -> tuple[list[dict] | None, str]:
    """
    Validate parsed JSON against the expected teams schema.
    Returns (teams_list, "") on success or (None, error_message) on failure.
    """
    if not isinstance(raw, dict) or "teams" not in raw:
        return None, 'JSON must be an object containing a "teams" key.'

    teams = raw["teams"]
    if not isinstance(teams, list):
        return None, '"teams" must be a list.'
    if not teams:
        return None, '"teams" list is empty.'

    existing_names = {t["team_name"].strip().lower() for t in st.session_state["teams"]}
    seen_names: set[str] = set()

    for ti, team in enumerate(teams, start=1):
        tname = team.get("team_name", "")
        pname = team.get("project_name", "")
        members = team.get("members", [])

        if not isinstance(tname, str) or not tname.strip():
            return None, f'Team #{ti}: "team_name" is missing or empty.'
        if not isinstance(pname, str) or not pname.strip():
            return None, f'Team #{ti} ({tname}): "project_name" is missing or empty.'
        if not isinstance(members, list) or not members:
            return None, f'Team #{ti} ({tname}): "members" must be a non-empty list.'

        norm = tname.strip().lower()
        if norm in existing_names:
            return None, f'Team "{tname}" already exists in the current session.'
        if norm in seen_names:
            return None, f'Duplicate team name "{tname}" found in the uploaded file.'
        seen_names.add(norm)

        seen_usernames: set[str] = set()
        for mi, member in enumerate(members, start=1):
            mname = member.get("name", "")
            musername = member.get("username", "")
            if not isinstance(musername, str) or not musername.strip():
                return None, (
                    f'Team "{tname}", member #{mi}: "username" is missing or empty.'
                )
            if not isinstance(mname, str):
                return None, (
                    f'Team "{tname}", member #{mi}: "name" must be a string.'
                )
            ukey = musername.strip().lower()
            if ukey in seen_usernames:
                return None, (
                    f'Team "{tname}": duplicate username "{musername}".'
                )
            seen_usernames.add(ukey)

    return teams, ""


def _render_json_upload() -> None:
    """
    Render the JSON bulk-upload section inside an expander.
    Appends validated teams to st.session_state["teams"].
    """
    import json

    with st.expander("📂 Upload JSON File", expanded=True):
        st.markdown(
            "Upload a `.json` file to import multiple teams at once. "
            "Existing teams will **not** be overwritten."
        )
        _SAMPLE_JSON = (
            "{"
            + '\n  "teams": ['
            + '\n    {'
            + '\n      "team_name": "Team Alpha",'
            + '\n      "project_name": "Project A",'
            + '\n      "members": ['
            + '\n        { "name": "John", "username": "john123" }'
            + '\n      ]'
            + '\n    }'
            + '\n  ]'
            + '\n}'
        )
        st.code(_SAMPLE_JSON, language="json")

        uploaded = st.file_uploader(
            "Choose a JSON file",
            type=["json"],
            key="_lb_json_uploader",
            label_visibility="collapsed",
        )

        if uploaded is None:
            return

        st.caption(f"📄 Uploaded: **{uploaded.name}**")

        raw_bytes = uploaded.read()
        if not raw_bytes:
            st.error("The uploaded file is empty.")
            return

        try:
            raw_data = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Could not parse JSON: {exc}")
            return

        teams_to_add, err = _validate_json_teams(raw_data)
        if err:
            st.error(f"Validation error: {err}")
            return

        # Normalise member dicts (ensure user_id key exists)
        clean_teams = [
            {
                "team_name":    t["team_name"].strip(),
                "project_name": t["project_name"].strip(),
                "members": [
                    {
                        "name":     m.get("name", "").strip(),
                        "username": m["username"].strip(),
                        "user_id":  m.get("user_id") or None,
                    }
                    for m in t["members"]
                ],
            }
            for t in teams_to_add
        ]

        st.session_state["teams"].extend(clean_teams)
        st.session_state["_lb_show_upload_form"] = False
        st.session_state["_lb_triggered"] = False
        st.success(
            f"✅ {len(clean_teams)} team(s) imported successfully: "
            + ", ".join(f'**{t["team_name"]}**' for t in clean_teams)
        )
        st.rerun()


# ---------------------------------------------------------------------------
# UI: Create Team Form
# ---------------------------------------------------------------------------


def _render_create_team_form() -> None:
    """Expandable form for creating a brand-new team."""
    # Don't show either form while an edit is active
    if st.session_state.get("edit_team_index") is not None:
        return

    # Two-button header: Create | Upload JSON
    btn_col1, btn_col2 = st.columns([1, 1])

    with btn_col1:
        create_label = (
            "✖ Cancel" if st.session_state["_lb_show_create_form"] else "➕ Create New Team"
        )
        if st.button(create_label, key="_lb_toggle_form", use_container_width=True):
            st.session_state["_lb_show_create_form"] = not st.session_state["_lb_show_create_form"]
            st.session_state["_lb_show_upload_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    with btn_col2:
        upload_label = (
            "✖ Cancel Upload" if st.session_state["_lb_show_upload_form"]
            else "📂 Add All Teams Using JSON"
        )
        if st.button(upload_label, key="_lb_toggle_upload", use_container_width=True):
            st.session_state["_lb_show_upload_form"] = not st.session_state["_lb_show_upload_form"]
            st.session_state["_lb_show_create_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    # Show whichever panel is active
    if st.session_state["_lb_show_upload_form"]:
        _render_json_upload()
        return

    if not st.session_state["_lb_show_create_form"]:
        return

    st.markdown("#### 🆕 New Team")
    col_a, col_b = st.columns(2)
    with col_a:
        team_name = st.text_input(
            "Team Name *", key="_lb_new_team_name", placeholder="e.g. Team Alpha"
        )
    with col_b:
        project_name = st.text_input(
            "Project Name", key="_lb_new_project_name", placeholder="e.g. Project Phoenix"
        )

    st.markdown("##### ➕ Add Members")
    mc1, mc2, mc3 = st.columns([2, 2, 1])
    with mc1:
        m_name = st.text_input("Member Name", key="_lb_c_m_name", placeholder="John Doe")
    with mc2:
        m_user = st.text_input("GitLab Username *", key="_lb_c_m_user", placeholder="john_doe")
    with mc3:
        m_id = st.number_input("User ID (opt.)", key="_lb_c_m_id", min_value=0, step=1, value=0)

    if st.button("➕ Add Member", key="_lb_create_add_member"):
        if not m_user.strip():
            st.warning("GitLab Username is required.")
        elif m_user.strip().lower() in [
            x["username"].lower() for x in st.session_state["_lb_draft_members"]
        ]:
            st.warning(f"**{m_user}** is already in the list.")
        else:
            st.session_state["_lb_draft_members"].append(
                {
                    "name": m_name.strip(),
                    "username": m_user.strip(),
                    "user_id": int(m_id) if m_id else None,
                }
            )
            st.rerun()

    if st.session_state["_lb_draft_members"]:
        st.markdown("**Members added so far:**")
        st.dataframe(
            pd.DataFrame(st.session_state["_lb_draft_members"]),
            use_container_width=True,
            hide_index=True,
        )
        rm_user = st.selectbox(
            "Remove a member",
            key="_lb_create_rm_select",
            options=["— select —"] + [m["username"] for m in st.session_state["_lb_draft_members"]],
        )
        if st.button("🗑 Remove Selected Member", key="_lb_create_rm_btn"):
            if rm_user != "— select —":
                st.session_state["_lb_draft_members"] = [
                    m for m in st.session_state["_lb_draft_members"] if m["username"] != rm_user
                ]
                st.rerun()
    else:
        st.info("No members added yet.")

    st.markdown("---")
    if st.button("💾 Save Team", type="primary", key="_lb_save_team"):
        if not team_name.strip():
            st.error("Team Name is required.")
        elif not st.session_state["_lb_draft_members"]:
            st.error("Add at least one member before saving.")
        elif _team_name_exists(team_name):
            st.error(f'A team named **"{team_name}"** already exists.')
        else:
            st.session_state["teams"].append(
                {
                    "team_name": team_name.strip(),
                    "project_name": project_name.strip(),
                    "members": list(st.session_state["_lb_draft_members"]),
                }
            )
            st.session_state["_lb_draft_members"] = []
            st.session_state["_lb_show_create_form"] = False
            st.session_state["_lb_triggered"] = False
            st.success(f'✅ Team **"{team_name}"** saved!')
            st.rerun()


# ---------------------------------------------------------------------------
# UI: Edit Team Form
# ---------------------------------------------------------------------------


def _render_edit_form(edit_idx: int) -> None:
    """
    Render a pre-filled editable form for the team at `edit_idx`.
    Uses _lb_edit_draft in session state as the working copy.
    """
    team = st.session_state["teams"][edit_idx]

    # Initialise draft when first entering edit for this team
    draft = st.session_state["_lb_edit_draft"]
    if draft.get("_source_index") != edit_idx:
        st.session_state["_lb_edit_draft"] = copy.deepcopy(team)
        st.session_state["_lb_edit_draft"]["_source_index"] = edit_idx
        draft = st.session_state["_lb_edit_draft"]

    st.markdown(f"#### ✏️ Editing: **{team['team_name']}**")

    col_a, col_b = st.columns(2)
    with col_a:
        new_team_name = st.text_input(
            "Team Name *", value=draft["team_name"], key="_lb_edit_team_name"
        )
    with col_b:
        new_project_name = st.text_input(
            "Project Name", value=draft.get("project_name", ""), key="_lb_edit_project_name"
        )

    st.markdown("##### 👥 Current Members")

    members: list[dict] = draft.get("members", [])
    if not members:
        st.info("No members. Add one below.")
    else:
        for m_idx, member in enumerate(members):
            mc1, mc2, mc3, mc4 = st.columns([2, 2, 1, 1])
            with mc1:
                members[m_idx]["name"] = st.text_input(
                    "Name", value=member.get("name", ""), key=f"_lb_edit_m_name_{m_idx}"
                )
            with mc2:
                members[m_idx]["username"] = st.text_input(
                    "GitLab Username *",
                    value=member.get("username", ""),
                    key=f"_lb_edit_m_user_{m_idx}",
                )
            with mc3:
                uid = member.get("user_id") or 0
                members[m_idx]["user_id"] = (
                    st.number_input(
                        "User ID", value=int(uid), min_value=0, step=1, key=f"_lb_edit_m_id_{m_idx}"
                    )
                    or None
                )
            with mc4:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑", key=f"_lb_edit_rm_{m_idx}", help="Remove this member"):
                    st.session_state["_lb_edit_draft"]["members"].pop(m_idx)
                    st.rerun()

    st.markdown("##### ➕ Add New Member")
    nc1, nc2, nc3 = st.columns([2, 2, 1])
    with nc1:
        new_m_name = st.text_input("Member Name", key="_lb_edit_new_m_name", placeholder="Jane Doe")
    with nc2:
        new_m_user = st.text_input(
            "GitLab Username *", key="_lb_edit_new_m_user", placeholder="jane_doe"
        )
    with nc3:
        new_m_id = st.number_input(
            "User ID (opt.)", key="_lb_edit_new_m_id", min_value=0, step=1, value=0
        )

    if st.button("➕ Add Member", key="_lb_edit_add_member"):
        if not new_m_user.strip():
            st.warning("GitLab Username is required.")
        elif new_m_user.strip().lower() in [
            m["username"].lower() for m in st.session_state["_lb_edit_draft"]["members"]
        ]:
            st.warning(f"**{new_m_user}** is already in the list.")
        else:
            st.session_state["_lb_edit_draft"]["members"].append(
                {
                    "name": new_m_name.strip(),
                    "username": new_m_user.strip(),
                    "user_id": int(new_m_id) if new_m_id else None,
                }
            )
            st.rerun()

    st.markdown("---")
    btn_col1, btn_col2, _ = st.columns([1, 1, 4])

    with btn_col1:
        if st.button("💾 Update Team", type="primary", key="_lb_edit_save"):
            # Sync text inputs back (Streamlit updates widget keys on rerun)
            draft["team_name"] = new_team_name
            draft["project_name"] = new_project_name

            # Validation
            if not new_team_name.strip():
                st.error("Team Name cannot be empty.")
            elif not draft.get("members"):
                st.error("Team must have at least one member.")
            elif _team_name_exists(new_team_name, exclude_index=edit_idx):
                st.error(f'Another team named **"{new_team_name}"** already exists.')
            else:
                # Commit draft → actual team list
                clean = {
                    "team_name": new_team_name.strip(),
                    "project_name": new_project_name.strip(),
                    "members": [
                        {k: v for k, v in m.items() if k != "_source_index"}
                        for m in draft["members"]
                        if m.get("username", "").strip()
                    ],
                }
                st.session_state["teams"][edit_idx] = clean
                st.session_state["edit_team_index"] = None
                st.session_state["_lb_edit_draft"] = {}
                st.session_state["_lb_triggered"] = False  # require re-run after edit
                st.success(f'✅ Team **"{new_team_name}"** updated!')
                st.rerun()

    with btn_col2:
        if st.button("✖ Cancel", key="_lb_edit_cancel"):
            st.session_state["edit_team_index"] = None
            st.session_state["_lb_edit_draft"] = {}
            st.rerun()


# ---------------------------------------------------------------------------
# UI: Teams Overview & Management
# ---------------------------------------------------------------------------


def _render_teams_overview() -> None:
    """Show all configured teams with Edit and Delete controls."""
    teams: list[dict] = st.session_state["teams"]
    active_edit = st.session_state.get("edit_team_index")

    if not teams:
        st.info("No teams created yet. Use **➕ Create New Team** to get started.")
        return

    st.markdown(f"**{len(teams)} team(s) configured:**")

    for idx, team in enumerate(teams):
        members = team.get("members", [])
        project = team.get("project_name", "—") or "—"
        usernames = ", ".join(m["username"] for m in members) or "—"

        # If this team is being edited, render the edit form inline
        if active_edit == idx:
            _render_edit_form(idx)
            st.divider()
            continue

        col_info, col_edit, col_del = st.columns([6, 1, 1])
        with col_info:
            st.markdown(
                f"🏅 **{team['team_name']}** &nbsp;|&nbsp; "
                f"Project: _{project}_ &nbsp;|&nbsp; "
                f"Members ({len(members)}): `{usernames}`"
            )
        with col_edit:
            if st.button("✏️", key=f"_lb_edit_team_{idx}", help="Edit this team"):
                # Close create form if open
                st.session_state["_lb_show_create_form"] = False
                st.session_state["edit_team_index"] = idx
                st.session_state["_lb_edit_draft"] = {}  # reset so draft re-initialises
                st.rerun()
        with col_del:
            if st.button("🗑", key=f"_lb_del_team_{idx}", help="Delete this team"):
                st.session_state["teams"].pop(idx)
                if st.session_state.get("edit_team_index") == idx:
                    st.session_state["edit_team_index"] = None
                    st.session_state["_lb_edit_draft"] = {}
                st.session_state["_lb_triggered"] = False
                st.rerun()


# ---------------------------------------------------------------------------
# UI: Per-Team Result Section
# ---------------------------------------------------------------------------


def _render_team_result(
    team_name: str, project_name: str, member_rows: list[dict], totals: dict
) -> None:
    """Render analytics for one team: metrics, member table, group breakdown."""
    st.subheader(f"🏅 {team_name}")
    if project_name:
        st.caption(f"Project: {project_name}")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Team Score", totals["Team Score"])
    c2.metric("Total Commits", totals["Total Commits"])
    c3.metric("MR Merged", totals["MR Merged"])
    c4.metric("Issues Closed", totals["Issues Closed"])
    c5.metric("Members", len(member_rows))

    display_cols = [
        "Username",
        "Status",
        "Total Commits",
        "Morning Commits",
        "Afternoon Commits",
        "MR Created",
        "MR Merged",
        "MR Open",
        "MR Closed",
        "Issues Raised",
        "Issues Closed",
        "Groups",
        "Score",
    ]
    df = pd.DataFrame(member_rows)
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], use_container_width=True, hide_index=True)

    group_rows = [
        {"Username": r["Username"], "Groups": r.get("Groups", 0)}
        for r in member_rows
        if r.get("Status") == "Success"
    ]
    if group_rows:
        with st.expander("👥 Group Breakdown"):
            st.dataframe(pd.DataFrame(group_rows), use_container_width=True, hide_index=True)

    st.divider()


# ---------------------------------------------------------------------------
# UI: Overall Leaderboard
# ---------------------------------------------------------------------------


def _render_overall_leaderboard(team_data: dict) -> None:
    """Ranked leaderboard table + bar chart."""
    st.subheader("🏆 Overall Team Leaderboard")

    lb_rows = [
        {
            "Team": tn,
            "Project": meta.get("project_name", "—"),
            "Team Score": totals["Team Score"],
            "Total Commits": totals["Total Commits"],
            "MR Merged": totals["MR Merged"],
            "MR Created": totals["MR Created"],
            "Issues Closed": totals["Issues Closed"],
            "Issues Raised": totals["Issues Raised"],
        }
        for tn, (meta, _, totals) in team_data.items()
    ]
    df_lb = pd.DataFrame(lb_rows).sort_values("Team Score", ascending=False).reset_index(drop=True)
    df_lb.insert(0, "Rank", range(1, len(df_lb) + 1))
    st.dataframe(df_lb, use_container_width=True, hide_index=True)
    st.divider()

    st.subheader("📊 Team Score Comparison")
    if not df_lb.empty:
        st.bar_chart(df_lb.set_index("Team")[["Team Score"]])


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def render_team_leaderboard(client) -> None:
    """Main render function. Called from app.py with the GitLabClient instance."""
    _init_state()

    st.subheader("🏆 Team Leaderboard")
    st.markdown(
        "Create and manage teams, then run analytics to compare productivity scores.\n\n"
        "**Score formula:** `Commits × 1 + Merged MRs × 5 + Total MRs × 2 + Issues Closed × 3`"
    )
    st.divider()

    # ── Section 1: Create Team ────────────────────────────────────────────
    _render_create_team_form()
    st.divider()

    # ── Section 2: Teams Overview (with inline edit) ──────────────────────
    st.markdown("### 📋 Configured Teams")
    _render_teams_overview()
    st.divider()

    # ── Section 3: Analysis ───────────────────────────────────────────────
    teams: list[dict] = st.session_state["teams"]
    if not teams:
        st.info("Add at least one team above to enable analysis.")
        return

    # Disable Run while an edit is active
    if st.session_state.get("edit_team_index") is not None:
        st.info("💡 Finish editing the team above before running analysis.")
        return

    # ── Date range filter ─────────────────────────────────────────────────
    since_iso, until_iso = _render_date_filter()

    if st.button("▶️ Run Leaderboard Analysis", type="primary", key="_lb_run_btn"):
        st.session_state["_lb_triggered"] = True

    if not st.session_state.get("_lb_triggered"):
        st.info("Click **▶️ Run Leaderboard Analysis** to fetch data for all teams.")
        return

    # ── Fetch ─────────────────────────────────────────────────────────────
    team_data: dict = {}
    progress = st.progress(0, text="Fetching team data…")

    for idx, team in enumerate(teams):
        team_name = team["team_name"]
        project_name = team.get("project_name", "")
        usernames = [m["username"] for m in team.get("members", []) if m.get("username")]

        if not usernames:
            team_data[team_name] = (team, [], _aggregate_team_totals([]))
            progress.progress((idx + 1) / len(teams), text=f"Skipped: {team_name}")
            continue

        with st.spinner(f"Fetching **{team_name}** ({len(usernames)} member(s))…"):
            try:
                results = process_batch_users(
                    client,
                    usernames,
                    since=since_iso,
                    until=until_iso,
                )
            except Exception as exc:
                st.warning(f"⚠️ Could not fetch data for **{team_name}**: {exc}")
                results = []

        member_rows = [_extract_member_row(r) for r in results if r]
        totals = _aggregate_team_totals(member_rows)
        team_data[team_name] = (team, member_rows, totals)
        progress.progress((idx + 1) / len(teams), text=f"Done: {team_name}")

    progress.empty()

    if not team_data:
        st.error("No team data could be fetched. Check your GitLab connection.")
        return

    # ── Render results ────────────────────────────────────────────────────
    st.markdown("### 📊 Team Results")
    for team_name, (meta, member_rows, totals) in team_data.items():
        _render_team_result(team_name, meta.get("project_name", ""), member_rows, totals)

    _render_overall_leaderboard(team_data)

    # ── Export ────────────────────────────────────────────────────────────
    st.subheader("📥 Export Report")
    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    filename = f"team_leaderboard_{now_ist.strftime('%Y-%m-%d')}.xlsx"
    try:
        st.download_button(
            label="⬇️ Download Full Report (Excel)",
            data=_build_excel_export(team_data),
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as exc:
        st.error(f"Could not generate Excel export: {exc}")
