import datetime
import io

import pandas as pd
import streamlit as st

from gitlab_utils import batch
from gitlab_utils.projects import ProjectResolutionError, resolve_project

DEFAULT_ICFAI_USERS = """saikrishna_b
MohanaSriBhavitha
praneethashish
kanukuntagreeshma2004
vandana1735
vandana_rajuldev
Mukthanand21
Shanmukh16
Sathwikareddy_Damanagari
Sahasraa
laxmanreddypatlolla
Abhilash653
LagichettyKushal
Lakshy
Suma2304
koushik_18
kumari123
Habeebunissa
Bhaskar_Battula
Pranav_rs
Pavani_Pothuganti
prav2702"""

DEFAULT_RCTS_USERS = """vai5h
Saiharshavardhan
Rushika_1105
swarna_4539
satish05
aravindswamy
pavaninagireddi
jeevana_31
saiteja3005
SandhyaRani_111
klaxmi1908
Kaveri_Mamidi
dasari_Askhaya
Ashritha_P"""


def render_batch_mode_ui(client, report_type):
    st.subheader(f"🚀 Batch Analytics - {report_type}")

    default_value = DEFAULT_ICFAI_USERS if report_type == "ICFAI" else DEFAULT_RCTS_USERS

    user_input = st.text_area(
        "Enter Usernames (one per line)", height=300, value=default_value, placeholder="user1\nuser2\n..."
    )

    project_input = st.text_input(
        "Optional Project Filter (ID, path, or URL)",
        placeholder="12345 or group/subgroup/project or https://gitlab.com/group/project.git",
        help="Leave empty to analyze all projects.",
    ).strip()

    if st.button("Run Batch Analysis"):
        usernames = [line.strip() for line in user_input.splitlines() if line.strip()]
        if not usernames:
            st.warning("Please enter at least one username.")
            return

        st.info(f"Processing {len(usernames)} users...")

        project_id = None
        if project_input:
            try:
                resolved = resolve_project(client, project_input)
                project_id = resolved.project_id
                st.success(f"Project filter applied: {resolved.project.name_with_namespace} (ID: {project_id})")
            except ProjectResolutionError as e:
                if e.kind == "not_found":
                    st.error("Project Not Found: verify URL/path/ID.")
                elif e.kind == "permission_denied":
                    st.error("Permission denied: token does not have access to this project.")
                else:
                    st.error(str(e))
                return
            except Exception as e:
                st.error(f"Error resolving project: {e}")
                return

        with st.spinner("Fetching data in parallel..."):
            if project_id is not None:
                results = batch.process_batch_users_project_filtered(client, usernames, project_id)
            else:
                results = batch.process_batch_users(client, usernames)

        st.success("Batch processing complete!")

        # Prepare Data based on Report Type
        report_data = []

        for res in results:
            u = res.get("username")
            status = res.get("status")
            err = res.get("error", "")

            data = res.get("data", {})
            projects = data.get("projects", {})

            # Stats Access
            c_stats = data.get("commit_stats", {"total": 0, "morning_commits": 0, "afternoon_commits": 0})
            m_stats = data.get("mr_stats", {"total": 0, "merged": 0, "opened": 0, "closed": 0})
            i_stats = data.get("issue_stats", {"total": 0, "opened": 0, "closed": 0})

            p_personal = len(projects.get("personal", []))
            p_contributed = len(projects.get("contributed", []))
            g_count = len(data.get("groups", []))

            row = {}
            row["Username"] = u
            row["Status"] = status

            # Add Generation Timestamp
            now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            row["Report Date"] = now_ist.strftime("%Y-%m-%d")
            row["Report Time"] = now_ist.strftime("%I:%M %p")

            if status == "Success":
                if report_type == "ICFAI":
                    # ICFAI Columns
                    row["Personal Projects"] = p_personal
                    row["Contributed Projects"] = p_contributed
                    row["Total Commits"] = c_stats["total"]
                    row["Morning Count"] = c_stats["morning_commits"]
                    row["Afternoon Count"] = c_stats["afternoon_commits"]
                    row["MR Open"] = m_stats["opened"]
                    row["MR Closed"] = m_stats["closed"]
                    row["MR Merged"] = m_stats["merged"]
                    row["Issues Open"] = i_stats["opened"]
                    row["Issues Closed"] = i_stats["closed"]
                    row["Groups Count"] = g_count

                elif report_type == "RCTS":
                    # RCTS Columns
                    row["Total Projects"] = p_personal + p_contributed
                    row["Total Commits"] = c_stats["total"]
                    row["MR Total"] = m_stats["total"]
                    row["MR Merged"] = m_stats["merged"]
                    row["MR Pending"] = m_stats["opened"]
                    row["Issues Total"] = i_stats["total"]
                    row["Groups"] = g_count
                    row["Morning Active"] = "Yes" if c_stats["morning_commits"] > 0 else "No"
                    row["Afternoon Active"] = "Yes" if c_stats["afternoon_commits"] > 0 else "No"
            else:
                row["Error"] = err

            report_data.append(row)

        # Display Summary
        st.write(f"### 📊 Batch Summary ({report_type})")
        df_report = pd.DataFrame(report_data)
        st.dataframe(df_report, width="stretch")

        # Export
        try:
            output = io.BytesIO()
            now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
            today = now_ist.strftime("%Y-%m-%d")
            filename = f"{report_type}_Report_{today}.xlsx"

            with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                # Sheet 1: Report
                df_report.to_excel(writer, index=False, sheet_name="Report")

                # Sheet 2: Raw Errors (if any)
                errors = [r for r in report_data if r.get("Status") == "Error"]
                if errors:
                    pd.DataFrame(errors).to_excel(writer, index=False, sheet_name="Errors")

            st.download_button(
                label=f"Download {report_type} Report",
                data=output.getvalue(),
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )

        except Exception as e:
            st.error(f"Error creating Excel: {e}")
