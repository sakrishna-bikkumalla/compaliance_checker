"""
Team Leaderboard Mode — Backend Team Selection
----------------------------------------------
Uses backend-managed team definitions and a UI dropdown to select one team or all teams.
Fetches analytics via process_batch_users() and renders a ranked leaderboard.

Score formula:
    score = (merged_mrs * 5) + (total_commits * 1) + (issues_closed * 2.5)

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
import statistics
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from gitlab_utils.batch import (
    process_batch_users,
    process_batch_users_project_filtered,
)
from gitlab_utils.projects import ProjectResolutionError, resolve_project

BACKEND_TEAMS: list[dict] = [
    {
        "team_name": "Dev 3",
        "project_name": "Dev 3",
        "members": [
            {"name": "Sai Krishna", "username": "saikrishna_b"},
            {"name": "Bhavitha", "username": "MohanaSriBhavitha"},
            {"name": "Madavarapu Sai Harshavardhan", "username": "Saiharshavardhan"},
        ],
    },
    {
        "team_name": "Trinity",
        "project_name": "Trinity",
        "members": [
            {"name": "Praneeth Ashish", "username": "praneethashish"},
            {"name": "Vaishnavi Prabhala", "username": "vai5h"},
            {"name": "Greeshma Kanukunta", "username": "kanukuntagreeshma2004"},
        ],
    },
    {
        "team_name": "Sudo",
        "project_name": "Sudo",
        "members": [
            {"name": "Balannagari Vandana Reddy", "username": "vandana1735"},
            {"name": "Rajuldev Vandana", "username": "vandana_rajuldev"},
            {"name": "Challa lakshmi Pavani", "username": "lakshmipavani_20"},
        ],
    },
    {
        "team_name": "Trishul",
        "project_name": "Trishul",
        "members": [
            {"name": "Mukthananad Reddy", "username": "Mukthanand21"},
            {"name": "Lanke Shanmukha Varma", "username": "Shanmukh16"},
            {"name": "Maddula Rushika Sritha", "username": "Rushika_1105"},
        ],
    },
    {
        "team_name": "BrainStorm",
        "project_name": "BrainStorm",
        "members": [
            {"name": "Daliboina satish", "username": "satish05"},
            {"name": "Damanagari Sathwika", "username": "Sathwikareddy_Damanagari"},
            {"name": "C.Sahasra", "username": "Sahasraa"},
        ],
    },
    {
        "team_name": "Core",
        "project_name": "Core",
        "members": [
            {"name": "Abhilash", "username": "Abhilash653"},
            {"name": "kanda swarna rathna madhuri", "username": "swarna_4539"},
            {"name": "Laxman Reddy", "username": "laxmanredddypatlolla"},
        ],
    },
    {
        "team_name": "Magnum",
        "project_name": "Magnum",
        "members": [
            {"name": "Lagichetty Kushal", "username": "LagichettyKushal"},
            {"name": "Lakshy Yarlagadda", "username": "Lakshy"},
            {"name": "Nagi Reddy Pavani", "username": "pavaninagireddi"},
        ],
    },
    {
        "team_name": "TrioForce",
        "project_name": "TrioForce",
        "members": [
            {"name": "Aravindswamy", "username": "aravindswamy"},
            {"name": "Suma Reddy", "username": "Suma2304"},
            {"name": "Koushik Reddy", "username": "koushik_18"},
        ],
    },
    {
        "team_name": "Techops",
        "project_name": "Techops",
        "members": [
            {"name": "Prabhu kumari", "username": "kumari123"},
            {"name": "Habiba", "username": "Habeebunissa"},
            {"name": "Chesetti Sai Jeevana Jyothi", "username": "jeevana_31"},
        ],
    },
    {
        "team_name": "Mind ops",
        "project_name": "Mind ops",
        "members": [
            {"name": "Bhaskar", "username": "Bhaskar_Battula"},
            {"name": "Sai Teja", "username": "saiteja3005"},
            {"name": "Satya Pranavanadh", "username": "Pranav_rs"},
        ],
    },
]


def get_all_teams() -> list[dict]:
    """Return all backend-managed teams as a defensive copy."""
    return copy.deepcopy(BACKEND_TEAMS)


def get_team_by_name(team_name: str) -> dict | None:
    """Return one backend-managed team by name, if present."""
    normalized = (team_name or "").strip().lower()
    for team in BACKEND_TEAMS:
        if team["team_name"].strip().lower() == normalized:
            return copy.deepcopy(team)
    return None


def _get_combined_teams() -> tuple[list[dict], list[dict], list[dict]]:
    """Return (backend_teams, custom_teams, combined_unique_teams)."""
    backend_teams = get_all_teams()
    custom_teams: list[dict] = copy.deepcopy(st.session_state.get("teams", []))

    combined: list[dict] = []
    seen_team_names: set[str] = set()
    for team in backend_teams + custom_teams:
        team_name = (team.get("team_name") or "").strip()
        if not team_name:
            continue
        key = team_name.lower()
        if key in seen_team_names:
            continue
        seen_team_names.add(key)
        combined.append(team)

    return backend_teams, custom_teams, combined


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
        "_lb_from_date": None,  # date input value or None
        "_lb_to_date": None,  # date input value or None
        "_lb_clear_dates_requested": False,  # one-shot flag to clear date widgets safely
        "_lb_project_id": None,  # Resolved int or None
        "_lb_project_input": "",  # Raw string input
        "_lb_selected_team": "All Teams",
        "_lb_page": "Workspace",
        "_lb_last_ranking_rows": [],
        "_lb_cached_results": None,
        "_lb_last_filters": None,
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

    # Clear date-related UI + backend state before rendering widgets.
    # This avoids stale widget values surviving across reruns.
    if st.session_state.get("_lb_clear_dates_requested"):
        st.session_state["_lb_from_date"] = None
        st.session_state["_lb_to_date"] = None
        st.session_state["_lb_date_since"] = None
        st.session_state["_lb_date_until"] = None
        st.session_state["_lb_clear_dates_requested"] = False

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
            st.session_state["_lb_clear_dates_requested"] = True
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


def _render_project_filter(client) -> int | None:
    """
    Render UI for project-wise filtering.
    Validates Project ID or GitLab URL. Returns resolved project_id or None.
    """
    st.markdown("### 📂 Project Filter")
    project_input = st.text_input(
        "Enter Project ID, path, or GitLab Project URL",
        value=st.session_state.get("_lb_project_input", ""),
        placeholder="e.g. 123456 or group/subgroup/project or https://gitlab.com/group/project.git",
        help="Leave empty to analyze across all projects.",
        key="_lb_project_input_widget",
    )

    # Persist raw input
    st.session_state["_lb_project_input"] = project_input.strip()

    if not st.session_state["_lb_project_input"]:
        st.session_state["_lb_project_id"] = None
        st.caption("No project filter applied — searching across all projects.")
        st.divider()
        return None

    try:
        resolved = resolve_project(client, st.session_state["_lb_project_input"])
        st.session_state["_lb_project_id"] = resolved.project_id
        st.success(f"✅ Filtering by Project: **{resolved.project.name_with_namespace}** (ID: {resolved.project_id})")
    except ProjectResolutionError as e:
        if e.kind == "not_found":
            st.error("Project Not Found: verify URL/path/ID.")
        elif e.kind == "permission_denied":
            st.error("Permission denied: token does not have access to this project.")
        else:
            st.error(str(e))
        st.session_state["_lb_project_id"] = None
        return None
    except Exception as e:
        st.error(f"Error resolving project: {e}")
        st.session_state["_lb_project_id"] = None
        return None

    st.divider()
    return st.session_state["_lb_project_id"]


def _calculate_score(total_commits: int, merged_mrs: int, issues_closed: int) -> float:
    """Return individual productivity score."""
    return merged_mrs * 5 + total_commits * 1 + issues_closed * 2.5


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
            "Assigned MRs": 0,
            "Assigned MR Merged": 0,
            "Assigned MR Open": 0,
            "Assigned MR Closed": 0,
            "Issues Raised": 0,
            "Issues Closed": 0,
            "Assigned Issues": 0,
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
        "Assigned MRs": m.get("assigned_mrs", 0),
        "Assigned MR Merged": m.get("assigned_merged", 0),
        "Assigned MR Open": m.get("assigned_opened", 0),
        "Assigned MR Closed": m.get("assigned_closed", 0),
        "Issues Raised": i.get("total", 0),
        "Issues Closed": issues_closed,
        "Assigned Issues": i.get("assigned_issues", 0),
        "Groups": len(data.get("groups", [])),
        "Score": _calculate_score(total_commits, merged_mrs, issues_closed),
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
        "Assigned MRs": 0,
        "Assigned MR Merged": 0,
        "Assigned MR Open": 0,
        "Assigned MR Closed": 0,
        "Issues Raised": 0,
        "Issues Closed": 0,
        "Assigned Issues": 0,
        "Team Score": 0,
    }
    for row in member_rows:
        for key in totals:
            src = "Score" if key == "Team Score" else key
            totals[key] += row.get(src, 0)
    return totals


def _team_name_exists(name: str, exclude_index: int | None = None) -> bool:
    """Return True if a team with this name already exists (optionally skipping one index)."""
    normalized = name.strip().lower()

    for idx, t in enumerate(st.session_state["teams"]):
        if idx == exclude_index:
            continue
        if t["team_name"].strip().lower() == normalized:
            return True

    for t in BACKEND_TEAMS:
        if t["team_name"].strip().lower() == normalized:
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
    existing_names.update(t["team_name"].strip().lower() for t in BACKEND_TEAMS)
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
                return None, (f'Team "{tname}", member #{mi}: "username" is missing or empty.')
            if not isinstance(mname, str):
                return None, (f'Team "{tname}", member #{mi}: "name" must be a string.')
            ukey = musername.strip().lower()
            if ukey in seen_usernames:
                return None, (f'Team "{tname}": duplicate username "{musername}".')
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
            "Upload a `.json` file to import multiple teams at once. Existing teams will **not** be overwritten."
        )
        sample_json = (
            "{"
            + '\n  "teams": ['
            + "\n    {"
            + '\n      "team_name": "Team Alpha",'
            + '\n      "project_name": "Project A",'
            + '\n      "members": ['
            + '\n        { "name": "John", "username": "john123" }'
            + "\n      ]"
            + "\n    }"
            + "\n  ]"
            + "\n}"
        )
        st.code(sample_json, language="json")

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
                "team_name": t["team_name"].strip(),
                "project_name": t["project_name"].strip(),
                "members": [
                    {
                        "name": m.get("name", "").strip(),
                        "username": m["username"].strip(),
                        "user_id": m.get("user_id") or None,
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
            + ", ".join(f"**{t['team_name']}**" for t in clean_teams)
        )
        st.rerun()


# ---------------------------------------------------------------------------
# UI: Create Team Form
# ---------------------------------------------------------------------------


def _render_create_team_form() -> None:
    """Expandable form for creating a brand-new team."""
    backend_teams, custom_teams, all_teams = _get_combined_teams()
    is_editing = st.session_state.get("edit_team_index") is not None

    team_options = ["All Teams"] + [team["team_name"] for team in all_teams]
    current_selection = st.session_state.get("_lb_selected_team", "All Teams")
    if current_selection not in team_options:
        st.session_state["_lb_selected_team"] = "All Teams"

    # Top controls in one row: Select Team | Create | Upload
    sel_col, btn_col1, btn_col2 = st.columns([2, 1, 1])
    with sel_col:
        st.selectbox(
            "Select Team",
            options=team_options,
            key="_lb_selected_team",
            label_visibility="collapsed",
            help="Choose a specific team or keep All Teams to analyze everyone.",
        )
    with btn_col1:
        create_label = "✖ Cancel" if st.session_state["_lb_show_create_form"] else "➕ Create New Team"
        if st.button(create_label, key="_lb_toggle_form", use_container_width=True, disabled=is_editing):
            st.session_state["_lb_show_create_form"] = not st.session_state["_lb_show_create_form"]
            st.session_state["_lb_show_upload_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    with btn_col2:
        upload_label = "✖ Cancel Upload" if st.session_state["_lb_show_upload_form"] else "📂 Add All Teams Using JSON"
        if st.button(upload_label, key="_lb_toggle_upload", use_container_width=True, disabled=is_editing):
            st.session_state["_lb_show_upload_form"] = not st.session_state["_lb_show_upload_form"]
            st.session_state["_lb_show_create_form"] = False  # close the other panel
            st.session_state["_lb_draft_members"] = []
            st.rerun()

    st.caption(
        "Configured teams: "
        f"Backend **{len(backend_teams)}** + Custom **{len(custom_teams)}** | "
        f"Available in dropdown: **{len(all_teams)}**"
    )

    if is_editing:
        return

    # Show whichever panel is active
    if st.session_state["_lb_show_upload_form"]:
        _render_json_upload()
        return

    if not st.session_state["_lb_show_create_form"]:
        return

    st.markdown("#### 🆕 New Team")
    col_a, col_b = st.columns(2)
    with col_a:
        team_name = st.text_input("Team Name *", key="_lb_new_team_name", placeholder="e.g. Team Alpha")
    with col_b:
        project_name = st.text_input("Project Name", key="_lb_new_project_name", placeholder="e.g. Project Phoenix")

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
        elif m_user.strip().lower() in [x["username"].lower() for x in st.session_state["_lb_draft_members"]]:
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
        new_team_name = st.text_input("Team Name *", value=draft["team_name"], key="_lb_edit_team_name")
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
                    st.number_input("User ID", value=int(uid), min_value=0, step=1, key=f"_lb_edit_m_id_{m_idx}")
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
        new_m_user = st.text_input("GitLab Username *", key="_lb_edit_new_m_user", placeholder="jane_doe")
    with nc3:
        new_m_id = st.number_input("User ID (opt.)", key="_lb_edit_new_m_id", min_value=0, step=1, value=0)

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
# UI: Theme CSS Injection
# ---------------------------------------------------------------------------


def _inject_dark_css() -> None:
    """Inject scoped dark-theme CSS for the Team Leaderboard page."""
    bg = "#0f1117"
    card_bg = "#1a1d2e"
    card_border = "#2d3154"
    accent = "#4f8ef7"
    text = "#e8eaf0"
    sub_text = "#8892a4"
    metric_bg = "#242840"
    metric_val = "#4f8ef7"
    badge_date = "#1b3a5c"
    badge_proj = "#1b3845"
    badge_date_text = "#60aff0"
    badge_proj_text = "#34d399"
    header_bg = "linear-gradient(135deg, #1a1d2e 0%, #242840 100%)"

    css = f"""
    <style>
    /* ── Page background ── */
    section[data-testid="stMain"] {{
        background-color: {bg};
    }}

    /* ── LB header card ── */
    .lb-header {{
        background: {header_bg};
        border: 1px solid {card_border};
        border-radius: 14px;
        padding: 24px 28px 18px;
        margin-bottom: 24px;
    }}
    .lb-header h1 {{
        color: {text};
        font-size: 2rem;
        font-weight: 800;
        margin: 0 0 4px;
        letter-spacing: -0.5px;
    }}
    .lb-header p {{
        color: {sub_text};
        font-size: 0.95rem;
        margin: 0;
    }}
    .lb-header .formula {{
        display: inline-block;
        margin-top: 10px;
        background: {metric_bg};
        color: {accent};
        font-size: 0.82rem;
        font-family: monospace;
        padding: 4px 10px;
        border-radius: 6px;
        border: 1px solid {card_border};
    }}

    /* ── Filter card ── */
    .lb-filter-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-left: 4px solid {accent};
        border-radius: 12px;
        padding: 20px 22px 16px;
        margin-bottom: 20px;
    }}
    .lb-filter-title {{
        color: {accent};
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }}

    /* ── Run button glow ── */
    div[data-testid="stButton"] > button[kind="primary"] {{
        background: {accent} !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        letter-spacing: 0.03em;
        transition: box-shadow 0.2s ease, transform 0.15s ease;
        box-shadow: 0 2px 12px {accent}44;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        box-shadow: 0 4px 22px {accent}88 !important;
        transform: translateY(-1px);
    }}

    /* ── Active filter badges ── */
    .lb-badges {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 12px 0 20px;
    }}
    .lb-badge-date {{
        background: {badge_date};
        color: {badge_date_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid {badge_date_text}33;
    }}
    .lb-badge-project {{
        background: {badge_proj};
        color: {badge_proj_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid {badge_proj_text}33;
    }}
    .lb-badge-none {{
        background: transparent;
        color: {sub_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        border: 1px dashed {card_border};
    }}

    /* ── Section label ── */
    .lb-section-label {{
        color: {sub_text};
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 8px;
    }}

    /* ── Team card ── */
    .lb-team-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 14px;
        padding: 22px 24px 18px;
        margin-bottom: 28px;
        box-shadow: 0 2px 16px rgba(0,0,0,0.08);
    }}
    .lb-team-name {{
        color: {text};
        font-size: 1.25rem;
        font-weight: 800;
        margin: 0 0 2px;
    }}
    .lb-team-project {{
        color: {sub_text};
        font-size: 0.82rem;
        margin-bottom: 16px;
    }}

    /* ── Metric tiles ── */
    .lb-metrics {{
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px;
        margin-bottom: 18px;
    }}
    .lb-metric-tile {{
        background: {metric_bg};
        border: 1px solid {card_border};
        border-radius: 10px;
        padding: 12px 10px;
        text-align: center;
    }}
    .lb-metric-label {{
        color: {sub_text};
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 6px;
    }}
    .lb-metric-value {{
        color: {metric_val};
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1;
    }}

    /* ── Dataframe ── */
    div[data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {card_border};
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

    css = f"""
    <style>
    /* ── Page background ── */
    section[data-testid="stMain"] {{
        background-color: {bg};
    }}

    /* ── LB header card ── */
    .lb-header {{
        background: {header_bg};
        border: 1px solid {card_border};
        border-radius: 14px;
        padding: 24px 28px 18px;
        margin-bottom: 24px;
    }}
    .lb-header h1 {{
        color: {text};
        font-size: 2rem;
        font-weight: 800;
        margin: 0 0 4px;
        letter-spacing: -0.5px;
    }}
    .lb-header p {{
        color: {sub_text};
        font-size: 0.95rem;
        margin: 0;
    }}
    .lb-header .formula {{
        display: inline-block;
        margin-top: 10px;
        background: {metric_bg};
        color: {accent};
        font-size: 0.82rem;
        font-family: monospace;
        padding: 4px 10px;
        border-radius: 6px;
        border: 1px solid {card_border};
    }}

    /* ── Filter card ── */
    .lb-filter-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-left: 4px solid {accent};
        border-radius: 12px;
        padding: 20px 22px 16px;
        margin-bottom: 20px;
    }}
    .lb-filter-title {{
        color: {accent};
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        margin-bottom: 10px;
    }}

    /* ── Run button hover glow ── */
    div[data-testid="stButton"] > button[kind="primary"] {{
        background: {accent} !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        letter-spacing: 0.03em;
        transition: box-shadow 0.2s ease, transform 0.15s ease;
        box-shadow: 0 2px 12px {accent}44;
    }}
    div[data-testid="stButton"] > button[kind="primary"]:hover {{
        box-shadow: 0 4px 22px {accent}88 !important;
        transform: translateY(-1px);
    }}

    /* ── Active filter badges ── */
    .lb-badges {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin: 12px 0 20px;
    }}
    .lb-badge-date {{
        background: {badge_date};
        color: {badge_date_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid {badge_date_text}33;
    }}
    .lb-badge-project {{
        background: {badge_proj};
        color: {badge_proj_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        font-weight: 600;
        border: 1px solid {badge_proj_text}33;
    }}
    .lb-badge-none {{
        background: transparent;
        color: {sub_text};
        border-radius: 20px;
        padding: 5px 14px;
        font-size: 0.82rem;
        border: 1px dashed {card_border};
    }}

    /* ── Section label above team card ── */
    .lb-section-label {{
        color: {sub_text};
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        margin-bottom: 8px;
    }}

    /* ── Team card ── */
    .lb-team-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 14px;
        padding: 22px 24px 18px;
        margin-bottom: 28px;
        box-shadow: 0 2px 16px rgba(0,0,0,0.08);
    }}
    .lb-team-name {{
        color: {text};
        font-size: 1.25rem;
        font-weight: 800;
        margin: 0 0 2px;
    }}
    .lb-team-project {{
        color: {sub_text};
        font-size: 0.82rem;
        margin-bottom: 16px;
    }}

    /* ── Metric tiles inside team card ── */
    .lb-metrics {{
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 12px;
        margin-bottom: 18px;
    }}
    .lb-metric-tile {{
        background: {metric_bg};
        border: 1px solid {card_border};
        border-radius: 10px;
        padding: 12px 10px;
        text-align: center;
    }}
    .lb-metric-label {{
        color: {sub_text};
        font-size: 0.72rem;
        font-weight: 600;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-bottom: 6px;
    }}
    .lb-metric-value {{
        color: {metric_val};
        font-size: 1.5rem;
        font-weight: 800;
        line-height: 1;
    }}

    /* ── Dataframe table tweaks ── */
    div[data-testid="stDataFrame"] {{
        border-radius: 10px;
        overflow: hidden;
        border: 1px solid {card_border};
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


def _render_active_filters_badges(since_iso, until_iso, project_id) -> None:
    """Render active filters as modern pill badges."""
    badges_html = '<div class="lb-badges">'
    has_filter = False

    if since_iso and until_iso:
        has_filter = True
        from_str = since_iso[:10]
        to_str = until_iso[:10]
        badges_html += f'<span class="lb-badge-date">📅 Date: {from_str} → {to_str}</span>'

    if bool(project_id):
        has_filter = True
        proj_label = st.session_state.get("_lb_project_input", str(project_id))
        # Truncate long URLs for display
        if len(proj_label) > 48:
            proj_label = "..." + proj_label[-45:]
        badges_html += f'<span class="lb-badge-project">🗂 Project: {proj_label}</span>'

    if not has_filter:
        badges_html += '<span class="lb-badge-none">🔍 No filters — full history</span>'

    badges_html += "</div>"
    st.markdown(badges_html, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# UI: Per-Team Result Section
# ---------------------------------------------------------------------------


def _render_team_result(team_name: str, project_name: str, member_rows: list[dict], totals: dict) -> None:
    """Render analytics for one team as a modern card with metrics and member table."""
    proj_line = f'<div class="lb-team-project">📂 {project_name}</div>' if project_name else ""

    metrics_html = f"""
    <div class="lb-team-card">
        <div class="lb-team-name">🏅 {team_name}</div>
        {proj_line}
        <div class="lb-metrics">
            <div class="lb-metric-tile">
                <div class="lb-metric-label">Team Score</div>
                <div class="lb-metric-value">{totals["Team Score"]}</div>
            </div>
            <div class="lb-metric-tile">
                <div class="lb-metric-label">Commits</div>
                <div class="lb-metric-value">{totals["Total Commits"]}</div>
            </div>
            <div class="lb-metric-tile">
                <div class="lb-metric-label">MR Merged</div>
                <div class="lb-metric-value">{totals["MR Merged"]}</div>
            </div>
            <div class="lb-metric-tile">
                <div class="lb-metric-label">Issues Closed</div>
                <div class="lb-metric-value">{totals["Issues Closed"]}</div>
            </div>
            <div class="lb-metric-tile">
                <div class="lb-metric-label">Members</div>
                <div class="lb-metric-value">{len(member_rows)}</div>
            </div>
        </div>
    </div>
    """
    st.markdown(metrics_html, unsafe_allow_html=True)

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
        "Assigned MRs",
        "Assigned MR Merged",
        "Assigned MR Open",
        "Assigned MR Closed",
        "Issues Raised",
        "Issues Closed",
        "Assigned Issues",
        "Groups",
        "Score",
    ]
    df = pd.DataFrame(member_rows)
    available = [c for c in display_cols if c in df.columns]
    st.dataframe(df[available], use_container_width=True, hide_index=True)

    group_rows = [
        {"Username": r["Username"], "Groups": r.get("Groups", 0)} for r in member_rows if r.get("Status") == "Success"
    ]
    if group_rows:
        with st.expander("👥 Group Breakdown"):
            st.dataframe(pd.DataFrame(group_rows), use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# UI: Overall Leaderboard
# ---------------------------------------------------------------------------


def _render_overall_leaderboard(team_data: dict) -> None:
    """Ranked leaderboard table + bar chart."""
    st.markdown(
        '<div class="lb-section-label">📊 Overall Leaderboard</div>',
        unsafe_allow_html=True,
    )
    st.markdown("### 🏆 Team Rankings")

    lb_rows = [
        {
            "Team": tn,
            "Project": meta.get("project_name", "—"),
            "Team Score": totals["Team Score"],
            "Total Commits": totals["Total Commits"],
            "MR Merged": totals["MR Merged"],
            "MR Created": totals["MR Created"],
            "Assigned MR Merged": totals["Assigned MR Merged"],
            "Assigned MR Open": totals["Assigned MR Open"],
            "Assigned MR Closed": totals["Assigned MR Closed"],
            "Issues Closed": totals["Issues Closed"],
            "Issues Raised": totals["Issues Raised"],
        }
        for tn, (meta, _, totals) in team_data.items()
    ]
    df_lb = pd.DataFrame(lb_rows).sort_values("Team Score", ascending=False).reset_index(drop=True)
    df_lb.insert(0, "Rank", range(1, len(df_lb) + 1))
    st.dataframe(df_lb, use_container_width=True, hide_index=True)
    st.divider()


def _build_ranking_rows(team_data: dict) -> list[dict]:
    """Create sorted ranking rows from already aggregated team totals."""
    rows = []
    for team_name, (_, _, totals) in team_data.items():
        rows.append(
            {
                "Team Name": team_name,
                "Total Score": totals.get("Team Score", 0),
                "Total Commits": totals.get("Total Commits", 0),
                "MRs Merged": totals.get("MR Merged", 0),
                "Issues Closed": totals.get("Issues Closed", 0),
            }
        )

    rows.sort(key=lambda x: x["Total Score"], reverse=True)
    ranked_rows = []
    for idx, row in enumerate(rows, start=1):
        ranked_rows.append(
            {
                "Rank": idx,
                "Badge": "",
                **row,
            }
        )
    return ranked_rows


def _build_individual_rows(team_data: dict) -> list[dict]:
    """Flatten all members across teams into a ranked list with achievement badges."""
    all_members: list[dict] = []
    for team_name, (_, member_rows, _) in team_data.items():
        for row in member_rows:
            if row.get("Status") != "Success":
                continue
            all_members.append(
                {
                    "Username": row.get("Username", "unknown"),
                    "Team Name": team_name,
                    "Total Commits": row.get("Total Commits", 0),
                    "MRs Merged": row.get("MR Merged", 0),
                    "Issues Closed": row.get("Issues Closed", 0),
                    "Score": row.get("Score", 0),
                    "Badge": "",
                }
            )

    all_members.sort(key=lambda x: x["Score"], reverse=True)

    # Track badges per member (max 3 each)
    MAX_BADGES = 3
    member_badges: dict[str, list[str]] = {m["Username"]: [] for m in all_members}

    def _can_badge(username: str) -> bool:
        return len(member_badges[username]) < MAX_BADGES

    def _add_badge(username: str, badge_name: str) -> None:
        member_badges[username].append(badge_name)

    # --- Team Player: highest scorer in each team ---
    teams_seen: set[str] = set()
    for m in all_members:
        team = m["Team Name"]
        if team not in teams_seen and m["Score"] > 0:
            _add_badge(m["Username"], "team_player")
            teams_seen.add(team)

    # --- Global achievement badges (a person can hold multiple) ---
    def _best_for(key: str, badge_name: str) -> None:
        for m in sorted(all_members, key=lambda x: x[key], reverse=True):
            if not _can_badge(m["Username"]):
                continue
            if badge_name in member_badges[m["Username"]]:
                continue
            if m[key] > 0:
                _add_badge(m["Username"], badge_name)
                return

    def _best_consistency(badge_name: str) -> None:
        candidates = [
            m
            for m in all_members
            if _can_badge(m["Username"])
            and badge_name not in member_badges[m["Username"]]
            and m["Total Commits"] > 0
            and m["MRs Merged"] > 0
            and m["Issues Closed"] > 0
        ]
        if not candidates:
            return
        best = min(
            candidates,
            key=lambda m: (
                statistics.stdev([m["Total Commits"], m["MRs Merged"], m["Issues Closed"]])
                / max(statistics.mean([m["Total Commits"], m["MRs Merged"], m["Issues Closed"]]), 1)
            ),
        )
        _add_badge(best["Username"], badge_name)

    _best_for("Score", "sprint_star")
    _best_for("Total Commits", "top_committer")
    _best_for("MRs Merged", "merge_master")
    # hackathon_hero: highest combined total
    for m in sorted(
        all_members,
        key=lambda x: x["Total Commits"] + x["MRs Merged"] + x["Issues Closed"],
        reverse=True,
    ):
        if (
            _can_badge(m["Username"])
            and "hackathon_hero" not in member_badges[m["Username"]]
            and (m["Total Commits"] + m["MRs Merged"] + m["Issues Closed"]) > 0
        ):
            _add_badge(m["Username"], "hackathon_hero")
            break
    _best_consistency("consistency_champ")

    # Write badges back to member dicts (list instead of single string)
    for m in all_members:
        m["Badges"] = member_badges[m["Username"]]

    # Assign serial numbers
    for idx, m in enumerate(all_members, start=1):
        m["S.No"] = idx

    return all_members


def _load_rank_badge_svg(rank: int) -> str:
    """Load badge SVG markup for ranks 1-6 from assets; otherwise return empty."""
    if rank < 1 or rank > 6:
        return ""

    repo_root = Path(__file__).resolve().parent.parent
    candidate_dirs = [
        repo_root / "badges",
        repo_root / "assets" / "badges",
        Path.home() / "Downloads" / "final badges",
        Path.home() / "Downloads" / "badges svg",
        Path.home() / "Downloads",
    ]

    explicit_names = [
        f"rank{rank}.svg",
        f"rank{rank} 1.svg",
        f"rank{rank} 2.svg",
    ]

    for folder in candidate_dirs:
        if not folder.exists():
            continue

        for name in explicit_names:
            badge_path = folder / name
            if badge_path.exists():
                try:
                    return badge_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        # Fallback for any alternate exported name like rank1_final.svg
        for badge_path in sorted(folder.glob(f"rank{rank}*.svg")):
            try:
                return badge_path.read_text(encoding="utf-8")
            except Exception:
                continue

    return ""


def _load_individual_badge_svg(badge_name: str) -> str:
    """Load badge SVG markup by achievement name from assets/badges/."""
    if not badge_name:
        return ""
    repo_root = Path(__file__).resolve().parent.parent
    badge_path = repo_root / "assets" / "badges" / f"{badge_name}.svg"
    if badge_path.exists():
        try:
            return badge_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return ""


def _render_ranking_table_html(ranked_rows: list[dict]) -> None:
    """Render ranking table with SVG badges using custom HTML/CSS."""
    table_rows: list[str] = []
    for row in ranked_rows:
        rank = int(row.get("Rank", 0))
        badge_svg = _load_rank_badge_svg(rank)

        if badge_svg:
            badge_html = f'<div class="lb-badge">{badge_svg}</div>'
        else:
            badge_html = ""

        table_rows.append(
            "<tr>"
            f'<td class="lb-rank">{rank}</td>'
            f'<td class="lb-badge-cell">{badge_html}</td>'
            f'<td class="lb-team">{escape(str(row.get("Team Name", "")))}</td>'
            f'<td class="lb-num">{int(row.get("Total Score", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Total Commits", 0))}</td>'
            f'<td class="lb-num">{int(row.get("MRs Merged", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Issues Closed", 0))}</td>'
            "</tr>"
        )

    html_table = f"""
<style>
.lb-rank-wrap {{
  width: 100%;
  overflow-x: auto;
}}
.lb-rank-table {{
  width: 100%;
  border-collapse: collapse;
  border-spacing: 0;
  background: rgba(18, 22, 30, 0.88);
  border: 1px solid rgba(120, 129, 149, 0.35);
  border-radius: 14px;
  overflow: hidden;
}}
.lb-rank-table thead th {{
  text-align: left;
  font-size: 17px;
  font-weight: 700;
  padding: 18px 16px;
  border-bottom: 1px solid rgba(120, 129, 149, 0.35);
  color: #e6edf7;
  letter-spacing: 0.01em;
  background: rgba(28, 33, 46, 0.95);
  white-space: nowrap;
}}
.lb-rank-table tbody td {{
  font-size: 18px;
  font-weight: 500;
  padding: 16px;
  border-bottom: 1px solid rgba(120, 129, 149, 0.24);
  color: #d9e1ee;
  vertical-align: middle;
}}
.lb-rank-table tbody tr:last-child td {{
  border-bottom: none;
}}
.lb-rank {{
  width: 80px;
  font-weight: 700;
  color: #f4f7ff;
}}
.lb-badge-cell {{
  min-width: 140px;
}}
.lb-badge {{
  width: 120px;
  min-height: 64px;
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
}}
.lb-badge svg {{
  width: 120px;
  height: auto;
  display: block;
}}
.lb-badge-label {{
  font-size: 11px;
  font-weight: 600;
  color: #a0b4d0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
}}
.lb-badges-row {{
  display: inline-flex;
  align-items: flex-start;
  gap: 12px;
  flex-wrap: wrap;
}}
.lb-team {{
  min-width: 220px;
  font-weight: 600;
}}
.lb-num {{
  min-width: 120px;
  white-space: nowrap;
}}
</style>
<div class="lb-rank-wrap">
  <table class="lb-rank-table">
    <thead>
      <tr>
        <th>Rank</th>
        <th>Badge</th>
        <th>Team Name</th>
        <th>Total Score</th>
        <th>Total Commits</th>
        <th>MRs Merged</th>
        <th>Issues Closed</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
</div>
"""
    st.markdown(html_table, unsafe_allow_html=True)


def _render_individual_table_html(individual_rows: list[dict]) -> None:
    """Render individual member ranking table with achievement badges."""
    _badge_display_names = {
        "team_player": "Team Player",
        "sprint_star": "Sprint Star",
        "top_committer": "Top Committer",
        "merge_master": "Merge Master",
        "hackathon_hero": "Hackathon Hero",
        "consistency_champ": "Consistency Champ",
    }

    table_rows: list[str] = []
    for row in individual_rows:
        badges = row.get("Badges", [])
        badge_parts: list[str] = []
        for badge_name in badges:
            svg = _load_individual_badge_svg(badge_name)
            if svg:
                label = _badge_display_names.get(badge_name, badge_name.replace("_", " ").title())
                badge_parts.append(
                    f'<div class="lb-badge">{svg}<span class="lb-badge-label">{escape(label)}</span></div>'
                )
        badge_html = f'<div class="lb-badges-row">{"".join(badge_parts)}</div>' if badge_parts else ""

        table_rows.append(
            "<tr>"
            f'<td class="lb-rank">{int(row.get("S.No", 0))}</td>'
            f'<td class="lb-badge-cell">{badge_html}</td>'
            f'<td class="lb-team">{escape(str(row.get("Username", "")))}</td>'
            f'<td class="lb-team">{escape(str(row.get("Team Name", "")))}</td>'
            f'<td class="lb-num">{int(row.get("Total Commits", 0))}</td>'
            f'<td class="lb-num">{int(row.get("MRs Merged", 0))}</td>'
            f'<td class="lb-num">{int(row.get("Issues Closed", 0))}</td>'
            "</tr>"
        )

    html_table = f"""
<div class="lb-rank-wrap">
  <table class="lb-rank-table">
    <thead>
      <tr>
        <th>S.No</th>
        <th>Badge</th>
        <th>Username</th>
        <th>Team Name</th>
        <th>Total Commits</th>
        <th>MRs Merged</th>
        <th>Issues Closed</th>
      </tr>
    </thead>
    <tbody>
      {"".join(table_rows)}
    </tbody>
  </table>
</div>
"""
    st.markdown(html_table, unsafe_allow_html=True)


def _render_ranking_page() -> None:
    """Ranking-only view that reuses previously computed summary rows."""
    st.markdown("### 🏅 Leaderboard Ranking")
    st.caption("Structured ranking table with badge placeholders for top 6 teams.")

    ranked_rows = st.session_state.get("_lb_last_ranking_rows", [])
    if not ranked_rows:
        st.info("No ranking data available yet. Go to **Workspace**, run analysis, then return here.")
        return

    _render_ranking_table_html(ranked_rows)

    # ── Individual Member Rankings ─────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 👤 Individual Member Rankings")
    st.caption(
        "All members ranked by individual score. "
        "Achievement badges: sprint_star, top_committer, merge_master, "
        "team_player, hackathon_hero, consistency_champ."
    )

    individual_rows = st.session_state.get("_lb_last_individual_rows", [])
    if individual_rows:
        _render_individual_table_html(individual_rows)
    else:
        st.info("No individual data available yet.")

    # ── Score Comparison Chart ─────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### 📊 Score Comparison")
    if ranked_rows:
        df_chart = pd.DataFrame(ranked_rows)
        # Map back to the expected columns for the chart
        if not df_chart.empty:
            chart_data = df_chart.rename(columns={"Team Name": "Team", "Total Score": "Team Score"})
            st.bar_chart(chart_data.set_index("Team")[["Team Score"]])


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------


def render_team_leaderboard(client) -> None:
    """Main render function. Called from app.py with the GitLabClient instance."""
    _init_state()

    _inject_dark_css()

    if "_lb_cached_results" not in st.session_state:
        st.session_state["_lb_cached_results"] = None
    if "_lb_last_filters" not in st.session_state:
        st.session_state["_lb_last_filters"] = None

    # ── Page header card ─────────────────────────────────────────────────
    st.markdown(
        """
        <div class="lb-header">
            <h1>🏆 Team Leaderboard</h1>
            <p>Compare team productivity across projects and time ranges.</p>
            <span class="formula">Score = Merged MRs × 5 + Commits × 1 + Issues Closed × 2.5</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Scoped UI Restyling CSS ──────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* Target buttons following the toggle marker */
        div:has(> .lb-toggle-container) + div button {
            border-radius: 10px !important;
            font-weight: 600 !important;
            padding: 0.75rem 1rem !important;
            transition: all 0.2s ease-in-out !important;
            border: none !important;
            height: 3rem !important;
        }

        /* Active Toggle (Primary) */
        div:has(> .lb-toggle-container) + div button[kind="primary"] {
            background-color: #d32f2f !important;
            color: white !important;
            box-shadow: 0 4px 12px rgba(211, 47, 47, 0.4) !important;
        }

        /* Inactive Toggle (Secondary) */
        div:has(> .lb-toggle-container) + div button[kind="secondary"] {
            background-color: #2c2c2c !important;
            color: #888 !important;
        }

        div:has(> .lb-toggle-container) + div button[kind="secondary"]:hover {
            background-color: #3d3d3d !important;
            color: #fff !important;
            transform: translateY(-1px);
        }

        /* Target button following the run marker */
        div:has(> .lb-run-btn) + div button {
            border-radius: 10px !important;
            font-weight: 700 !important;
            padding: 0.8rem !important;
            transition: all 0.2s ease-in-out !important;
            background-color: #d32f2f !important;
            color: white !important;
            box-shadow: 0 4px 12px rgba(211, 47, 47, 0.3) !important;
            width: 100% !important;
            border: none !important;
            height: 3.5rem !important;
        }

        div:has(> .lb-run-btn) + div button:hover {
            background-color: #b71c1c !important;
            transform: translateY(-2px);
            box-shadow: 0 6px 16px rgba(183, 28, 28, 0.5) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Page selector (Button Toggle) ────────────────────────────────────
    st.markdown('<div class="lb-toggle-container">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    current_page = st.session_state.get("_lb_page", "Workspace")

    with col1:
        if st.button(
            "Workspace",
            use_container_width=True,
            key="_btn_workspace",
            type="secondary" if current_page == "Leaderboard Ranking" else "primary",
        ):
            st.session_state["_lb_page"] = "Workspace"
            st.rerun()

    with col2:
        if st.button(
            "Leaderboard Ranking",
            use_container_width=True,
            key="_btn_ranking",
            type="secondary" if current_page == "Workspace" else "primary",
        ):
            st.session_state["_lb_page"] = "Leaderboard Ranking"
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    page = st.session_state["_lb_page"]
    st.divider()

    if page == "Leaderboard Ranking":
        _render_ranking_page()
        return

    # ── Section 1: Create / Upload Teams (existing options) ───────────────
    _render_create_team_form()
    st.divider()

    st.markdown("### 📋 Custom Teams")
    _render_teams_overview()
    st.divider()

    # ── Section 2: Team Selection (from top controls) ─────────────────────
    backend_teams, custom_teams, all_teams = _get_combined_teams()
    if not all_teams:
        st.error("No teams are configured.")
        return

    selected_team_name = st.session_state.get("_lb_selected_team", "All Teams")

    if selected_team_name == "All Teams":
        teams = all_teams
    else:
        selected_team = next(
            (team for team in all_teams if team.get("team_name", "").strip().lower() == selected_team_name.lower()),
            None,
        )
        teams = [selected_team] if selected_team else []

    if not teams:
        st.error("Selected team is not available in backend configuration.")
        return

    st.caption(f"Selected for run: **{len(teams)}**")
    st.divider()

    # ── Section 3: Analysis Filters ───────────────────────────────────────
    st.markdown(
        '<div class="lb-filter-card"><div class="lb-filter-title">🔎 Filters</div>',
        unsafe_allow_html=True,
    )
    since_iso, until_iso = _render_date_filter()
    project_id = _render_project_filter(client)
    st.markdown("</div>", unsafe_allow_html=True)

    # ── Run button ────────────────────────────────────────────────────────
    st.markdown('<div class="lb-run-btn">', unsafe_allow_html=True)
    run_button_clicked = st.button("▶️ Run Leaderboard Analysis", type="primary", key="_lb_run_btn")
    st.markdown("</div>", unsafe_allow_html=True)
    if run_button_clicked:
        st.session_state["_lb_triggered"] = True

    # ── Capture Filter Snapshot ───────────────────────────────────────────
    current_filters = {
        "teams": teams,
        "since": since_iso,
        "until": until_iso,
        "project_id": project_id,
    }

    # ── Prevent Recompute On Page Switch ──────────────────────────────────
    # We display whatever is in the cache regardless of current filter states.
    # Re-analysis is strictly triggered only by the Run button.
    team_data = st.session_state.get("_lb_cached_results")

    # ── Active filters display (read-only, updates on every rerun) ────────
    _active_filters: list[str] = []

    # Date filter — only show when both bounds are set
    if since_iso and until_iso:
        _from_str = since_iso[:10]
        _to_str = until_iso[:10]
        _active_filters.append(f"• 📅 Date: **{_from_str}** → **{_to_str}**")

    # Project filter — use resolved project_id from _render_project_filter
    if bool(project_id):
        _proj_label = st.session_state.get("_lb_project_input", str(project_id))
        _active_filters.append(f"• 🗂 Project: **{_proj_label}** (ID: `{project_id}`)")

    if _active_filters:
        st.markdown("🔎 **Active Filters:**\n\n" + "\n\n".join(_active_filters))
    else:
        st.info("🔎 **Active Filters:** None (Showing full history across all projects)")

    # ── Display stale-cache warning if filters changed ────────────────────
    if team_data is not None and st.session_state.get("_lb_last_filters") != current_filters:
        st.warning(
            "⚠️ **Filters have changed.** Displaying results from last analysis run. "
            "Click **Run Leaderboard Analysis** to update."
        )

    # ── Active filter badges ──────────────────────────────────────────────
    _render_active_filters_badges(since_iso, until_iso, project_id)

    # ── Fetch (Strictly only if button clicked) ───────────────────────────
    if run_button_clicked:
        team_data = {}
        progress = st.progress(0, text="Fetching team data…")

        for idx, team in enumerate(teams):
            team_name = team["team_name"]
            usernames = [m["username"] for m in team.get("members", []) if m.get("username")]

            if not usernames:
                team_data[team_name] = (team, [], _aggregate_team_totals([]))
                progress.progress((idx + 1) / len(teams), text=f"Skipped: {team_name}")
                continue

            results = []
            with st.spinner(f"Fetching **{team_name}** ({len(usernames)} member(s))…"):
                try:
                    if project_id:
                        results = process_batch_users_project_filtered(
                            client,
                            usernames,
                            project_id,
                            since=since_iso,
                            until=until_iso,
                        )
                    else:
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

        # Cache results
        st.session_state["_lb_cached_results"] = team_data
        st.session_state["_lb_last_filters"] = current_filters

        # Persist compact ranking summary for the separate ranking page.
        st.session_state["_lb_last_ranking_rows"] = _build_ranking_rows(team_data)
        st.session_state["_lb_last_individual_rows"] = _build_individual_rows(team_data)

    if team_data is None:
        st.info("Click **▶️ Run Leaderboard Analysis** to fetch data for selected team(s).")
        return

    # ── Render results ────────────────────────────────────────────────────
    st.markdown('<div class="lb-section-label">📊 Team Results</div>', unsafe_allow_html=True)
    for team_name, (meta, member_rows, totals) in team_data.items():
        _render_team_result(team_name, meta.get("project_name", ""), member_rows, totals)

    _render_overall_leaderboard(team_data)

    # ── Export ────────────────────────────────────────────────────────────
    st.markdown("### 📥 Export Report")
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
