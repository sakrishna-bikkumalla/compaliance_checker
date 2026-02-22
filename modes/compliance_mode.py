import streamlit as st
from gitlab_utils.projects import ProjectResolutionError, resolve_project

# --- Helper Functions (copied/adapted from app.py) ---

@st.cache_data(ttl=60)
def read_file_content(_project, file_path, ref):
    try:
        file = _project.files.get(file_path=file_path, ref=ref)
        return file.decode().decode("utf-8")
    except Exception:
        return None

def check_vscode_settings(project, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return "settings.json" in [item["name"].lower() for item in items]
    except Exception:
        return False

def check_vscode_file_exists(project, filename, branch="main"):
    try:
        items = project.repository_tree(path=".vscode", ref=branch)
        return filename.lower() in [item["name"].lower() for item in items]
    except Exception:
        return False

def check_license_content(project, branch="main"):
    content = read_file_content(project, "LICENSE", branch) or read_file_content(
        project, "LICENSE.md", branch
    )
    if not content:
        return "not_found"

    cleaned = " ".join(content.strip().split()).lower()
    has_affero = "affero" in cleaned
    has_gpl = "general public license" in cleaned
    has_version_3 = "version 3" in cleaned or "v3" in cleaned or "3.0" in cleaned
    has_correct_agpl_date = "19 november 2007" in cleaned

    if has_affero and has_gpl and has_version_3 and has_correct_agpl_date:
        return "valid"

    has_correct_gplv3_date = "29 june 2007" in cleaned
    is_gplv3 = has_gpl and has_version_3 and has_correct_gplv3_date and not has_affero
    has_lgpl = "lgpl" in cleaned or "lesser general public license" in cleaned
    has_correct_lgpl_date = "29 june 2007" in cleaned
    is_lgplv3 = has_lgpl and has_version_3 and has_correct_lgpl_date

    if is_gplv3 or is_lgplv3:
        return "gnu_other"

    has_gnu = "gnu" in cleaned
    has_gpl_v2 = "version 2" in cleaned or "v2" in cleaned or "2.0" in cleaned
    has_gpl_general = has_gpl and not has_affero

    if (
        (has_gnu and has_gpl_general and (has_version_3 or has_gpl_v2))
        or (has_lgpl and (has_version_3 or has_gpl_v2))
        or (has_gpl_general and (has_version_3 or has_gpl_v2))
    ):
        return "gnu_other"

    non_gnu_licenses = [
        "mit license", "apache license", "apache 2.0", "bsd license",
        "unlicense", "zlib", "isc license", "mozilla public license",
        "eclipse public license", "creative commons",
    ]
    if any(phrase in cleaned for phrase in non_gnu_licenses):
        return "invalid"

    if "license" in cleaned and "copyright" in cleaned:
        if has_gnu or has_gpl or has_lgpl:
            return "gnu_other"
        return "invalid"

    return "invalid"

def check_vscode_settings_content(project, branch="main"):
    content = read_file_content(project, ".vscode/settings.json", branch)
    return {"exists": content is not None}

def check_extensions_json_for_ruff(project, branch="main"):
    content = read_file_content(project, ".vscode/extensions.json", branch)
    if not content:
        return False
    try:
        import json
        config = json.loads(content)
        recommendations = config.get("recommendations", [])
        return "charliermarsh.ruff" in recommendations or any(
            "ruff" in ext.lower() for ext in recommendations
        )
    except Exception:
        return False

def check_templates_presence(project, branch="main"):
    result = {
        "issue_templates_folder": False,
        "issue_template_files": [],
        "merge_request_templates_folder": False,
        "merge_request_template_files": [],
    }
    try:
        items = project.repository_tree(path=".gitlab/issue_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["issue_templates_folder"] = True
            result["issue_template_files"] = md_files
    except Exception:
        pass
    try:
        items = project.repository_tree(path=".gitlab/merge_request_templates", ref=branch)
        md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
        if md_files:
            result["merge_request_templates_folder"] = True
            result["merge_request_template_files"] = md_files
    except Exception:
        pass
    return result

def check_project_compliance(project, branch=None):
    required_files = {
        "README.md": ["README.md"],
        "CONTRIBUTING.md": ["CONTRIBUTING.md"],
        "CHANGELOG": ["CHANGELOG", "CHANGELOG.md"],
    }
    report = {}
    try:
        branch = branch or getattr(project, "default_branch", "main")
        tree = project.repository_tree(ref=branch)
        filenames = [item["name"].lower() for item in tree]

        for label, variants in required_files.items():
            report[label] = any(variant.lower() in filenames for variant in variants)

        readme_present = any(n for n in filenames if n.startswith("readme"))
        report["README.md"] = readme_present
        if readme_present:
            content = read_file_content(project, "README.md", branch) or read_file_content(
                project, "README", branch
            )
            if not content or not content.strip():
                report["readme_status"] = "empty"
                report["readme_sections"] = []
                report["readme_needs_improvement"] = True
            else:
                lc = content.lower()
                expected_sections = [
                    "installation", "usage", "getting started", "setup",
                    "license", "contributing", "example", "quick start", "features",
                ]
                found_sections = [s for s in expected_sections if s in lc]
                report["readme_status"] = "present"
                report["readme_sections"] = found_sections
                report["readme_needs_improvement"] = (
                    len(found_sections) < 3 or len(content.strip()) < 150
                )
        else:
            report["readme_status"] = "missing"
            report["readme_sections"] = []
            report["readme_needs_improvement"] = True

        license_variants = ["LICENSE", "LICENSE.md"]
        report["LICENSE"] = any(variant.lower() in filenames for variant in license_variants)
        if report["LICENSE"]:
            license_status = check_license_content(project, branch)
        else:
            license_status = "not_found"
        report["license_valid"] = license_status == "valid"
        report["license_status"] = license_status

        report[".gitignore"] = ".gitignore" in filenames
        report["pyproject.toml"] = "pyproject.toml" in filenames
        report["uv_lock_exists"] = "uv.lock" in filenames
        report["vscode_settings"] = check_vscode_settings(project, branch)
        vscode_content = check_vscode_settings_content(project, branch)
        report["vscode_config_exists"] = vscode_content["exists"]
        report["vscode_ruff_in_extensions"] = check_extensions_json_for_ruff(project, branch)
        report["vscode_extensions_exists"] = check_vscode_file_exists(project, "extensions.json", branch)
        report["vscode_launch_exists"] = check_vscode_file_exists(project, "launch.json", branch)
        report["vscode_tasks_exists"] = check_vscode_file_exists(project, "tasks.json", branch)

        template_details = check_templates_presence(project, branch)
        report.update(template_details)

        report["description_present"] = bool(project.description and project.description.strip())
        report["tags_present"] = len(project.tags.list(per_page=1)) > 0

    except Exception as e:
        report["error"] = f"Error during compliance check: {e}"
    return report

def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []

def get_suggestions_for_missing_items(report):
    # (Copied from app.py - abridged for brevity but kept functional)
    suggestion_list = [
        ("README.md", "README.md missing", "Add a `README.md` file."),
        ("CONTRIBUTING.md", "CONTRIBUTING.md missing", "Add a `CONTRIBUTING.md` file."),
        ("CHANGELOG", "CHANGELOG missing", "Maintain a `CHANGELOG.md` file."),
        ("LICENSE", "LICENSE missing", "Include an `AGPLv3 LICENSE` file."),
        ("license_valid", "LICENSE is not AGPLv3", "Ensure the license is AGPLv3."),
        ("issue_templates_folder", "Issue templates folder missing", "Create `.gitlab/issue_templates/`."),
        ("merge_request_templates_folder", "Merge request templates folder missing", "Create `.gitlab/merge_request_templates/`."),
        (".gitignore", ".gitignore missing", "Add a `.gitignore` file."),
        ("pyproject.toml", "pyproject.toml missing", "Add a `pyproject.toml` file."),
        ("vscode_settings", ".vscode/settings.json missing", "Add a `.vscode/settings.json` file."),
        ("vscode_ruff_in_extensions", "Ruff not in .vscode/extensions.json", "Add `charliermarsh.ruff` to recommendations."),
        ("vscode_extensions_exists", ".vscode/extensions.json missing", "Add a `.vscode/extensions.json` file."),
        ("vscode_launch_exists", ".vscode/launch.json missing", "Add `.vscode/launch.json`."),
        ("vscode_tasks_exists", ".vscode/tasks.json missing", "Add `.vscode/tasks.json`."),
        ("description_present", "Project description missing", "Provide a project description."),
        ("tags_present", "Project tags missing", "Tag your project releases."),
        ("uv_lock_exists", "uv.lock missing", "Run `uv lock` to generate `uv.lock`."),
    ]

    st.subheader("📌 Suggestions for Missing Items")
    for key, display_name, suggestion_text in suggestion_list:
        if not report.get(key, True):
            st.markdown(f"❌ **{display_name}** — {suggestion_text}")

    readme_status = report.get("readme_status")
    if readme_status == "missing":
        st.markdown("❌ **README missing** — Add a `README.md`.")
    elif readme_status == "empty":
        st.markdown("❌ **README is empty** — Add meaningful content.")
    elif report.get("readme_needs_improvement"):
         st.markdown("🟡 **README needs improvement** — Consider adding Installation/Usage/License/Contributing.")

def render_project_compliance_ui(report, project=None, branch=None, classification=None):
    if report.get("error"):
        st.error(report["error"])
        return

    st.markdown("### 📋 Compliance Summary by Category")
    categories = {
        "1. 📄 Project Metadata": {
            "description_present": "Project Description",
            "tags_present": "Tags",
        },
        "2. 📚 Project Documentation": {
            "README.md": "README.md",
            "CONTRIBUTING.md": "CONTRIBUTING.md",
            "CHANGELOG": "CHANGELOG",
            "LICENSE": "LICENSE",
            "license_valid": "LICENSE should be AGPLv3",
            "issue_templates_folder": "Issue Templates Folder",
            "merge_request_templates_folder": "Merge Request Templates Folder",
            "readme_status": "README status",
        },
        "3. ⚙️ Project Configuration": {
            ".gitignore": ".gitignore",
            "pyproject.toml": "pyproject.toml",
            "uv_lock_exists": "uv.lock",
        },
        "4. 🖥️ IDE Setup": {
            "vscode_settings": ".vscode/settings.json",
            "vscode_ruff_in_extensions": "Ruff in config",
            "vscode_config_exists": "VSCode Config Exists", # Added missing key in rendering
             "vscode_extensions_exists": ".vscode/extensions.json",
        }
    }

    for cat_name, items in categories.items():
        st.markdown(f"**{cat_name}**")
        for key, label in items.items():
            status = report.get(key)
            if key == "readme_status":
                icon = "✅" if status == "present" and not report.get("readme_needs_improvement") else ("✅ (Needs Impr.)" if status == "present" else "❌")
            else:
                 icon = "✅" if status else "❌"
            st.write(f"{icon} {label}")

def render_compliance_mode(gl_client):
    st.subheader("🔍 Project Compliance Checker")

    tabs = st.tabs(["Single Project", "Batch Projects"])

    with tabs[0]:
        st.markdown("#### Check a Single Project")

        # State management for Single Project
        if 'compliance_project_id' not in st.session_state:
            st.session_state['compliance_project_id'] = ""

        project_input = st.text_input("Enter Project ID or URL",
                                      value=st.session_state['compliance_project_id'],
                                      key="single_project_input",
                                      placeholder="https://gitlab.com/group/project")

        col1, col2 = st.columns([1, 4])
        with col1:
             fetch_clicked = st.button("Fetch Project")

        if fetch_clicked and project_input:
            st.session_state['compliance_project_id'] = project_input
            try:
                with st.spinner("Fetching project..."):
                    resolved = resolve_project(gl_client, project_input)
                    project = resolved.project
                    st.session_state['current_project'] = project
                    st.session_state['current_project_branches'] = get_project_branches(project)
                    st.success(f"Loaded: **{project.name_with_namespace}**")
                    st.rerun()
            except ProjectResolutionError as e:
                if e.kind == "not_found":
                    st.error("Project Not Found: verify the URL/path/ID.")
                elif e.kind == "permission_denied":
                    st.error("Permission denied: your token cannot access this project.")
                else:
                    st.error(str(e))
            except Exception as e:
                st.error(f"Error fetching project: {e}")

        # Display Project Info & Run Analysis if loaded
        if 'current_project' in st.session_state and st.session_state.get('compliance_project_id') == project_input:
            project = st.session_state['current_project']
            st.info(f"Active Project: **{project.name_with_namespace}** ({project.web_url})")

            branches = st.session_state.get('current_project_branches', [])
            default_branch_idx = 0
            if hasattr(project, "default_branch") and project.default_branch in branches:
                default_branch_idx = branches.index(project.default_branch)

            branch = st.selectbox("Select Branch", branches, index=default_branch_idx)

            if st.button("Run Analysis", key="run_analysis_single"):
                 with st.spinner("Analyzing..."):
                    report = check_project_compliance(project, branch)
                    render_project_compliance_ui(report, project, branch)
                    get_suggestions_for_missing_items(report)

    with tabs[1]:
        st.markdown("#### Batch Check Multiple Projects")
        render_batch_project_compliance_internal(gl_client)

def render_batch_project_compliance_internal(gl_client):
    project_input = st.text_area(
        "Enter Project IDs or URLs (one per line)",
        height=150,
        placeholder="https://gitlab.com/group/project1\n12345\n..."
    )

    if st.button("Run Batch Analysis", key="run_batch_btn"):
        lines = [line.strip() for line in project_input.splitlines() if line.strip()]
        if not lines:
            st.warning("Please enter at least one project.")
            return

        results = []
        progress_bar = st.progress(0)

        for i, line in enumerate(lines):
            try:
                resolved = resolve_project(gl_client, line)
                project = resolved.project
                report = check_project_compliance(project)

                # Summarize for table
                row = {
                    "Project": project.name_with_namespace,
                    "URL": project.web_url,
                    "README": "✅" if report.get("readme_status") == "present" else "❌",
                    "LICENSE": "✅" if report.get("license_valid") else "❌",
                    "VSCode": "✅" if report.get("vscode_config_exists") else "❌",
                    "Metdata": "✅" if report.get("description_present") else "❌",
                    "CI/CD": "✅" if report.get(".gitlab-ci.yml") else "❌",
                    "GitProcess": "✅" if report.get("issue_templates_folder") or report.get("merge_request_templates_folder") else "❌"
                }

                if report.get("error"):
                    row["Error"] = report["error"]

                results.append(row)

            except ProjectResolutionError as e:
                results.append({"Project": line, "Error": str(e)})
            except Exception as e:
                results.append({"Project": line, "Error": str(e)})

            progress_bar.progress((i + 1) / len(lines))

        if results:
            st.write("### 📊 Batch Summary")
            st.dataframe(results)

            # Excel Export
            try:
                import pandas as pd
                from io import BytesIO
                df = pd.DataFrame(results)
                output = BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    df.to_excel(writer, index=False, sheet_name='Batch Compliance')
                st.download_button(
                    label="Download Batch Report",
                    data=output.getvalue(),
                    file_name="batch_compliance_report.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except Exception:
                pass
