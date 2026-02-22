from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse


@dataclass
class ResolvedProject:
    project_id: int
    project_path: str | None
    encoded_path: str | None
    project: Any


class ProjectResolutionError(Exception):
    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind


def _unwrap_gitlab_client(client_or_wrapper: Any) -> Any:
    if hasattr(client_or_wrapper, "projects"):
        return client_or_wrapper

    inner = getattr(client_or_wrapper, "client", None)
    if inner is not None and hasattr(inner, "projects"):
        return inner

    raise ProjectResolutionError("GitLab client is not initialized.", kind="client_error")


def normalize_project_input(project_input: str) -> tuple[int | None, str | None, str | None]:
    raw = (project_input or "").strip()
    if not raw:
        raise ProjectResolutionError("Project input cannot be empty.", kind="invalid_input")

    if raw.isdigit():
        return int(raw), None, None

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        path = (parsed.path or "").strip("/")
    else:
        path = raw.strip("/")

    if path.endswith(".git"):
        path = path[:-4]

    path = path.strip("/")
    if not path:
        raise ProjectResolutionError(
            "Invalid project input. Provide a project URL, path, or numeric ID.",
            kind="invalid_input",
        )

    return None, path, quote(path, safe="")


def _status_code_from_exception(exc: Exception) -> int | None:
    response_code = getattr(exc, "response_code", None)
    if isinstance(response_code, int):
        return response_code

    response = getattr(exc, "response", None)
    if response is not None:
        status_code = getattr(response, "status_code", None)
        if isinstance(status_code, int):
            return status_code

    return None


def _classify_resolution_error(exc: Exception) -> ProjectResolutionError:
    status = _status_code_from_exception(exc)
    if status == 404:
        return ProjectResolutionError("Project Not Found", kind="not_found")
    if status in (401, 403):
        return ProjectResolutionError(
            "Permission denied. Token does not have access to this project.",
            kind="permission_denied",
        )
    return ProjectResolutionError(f"Failed to resolve project: {exc}", kind="unknown")


def resolve_project(client_or_wrapper: Any, project_input: str) -> ResolvedProject:
    gl_client = _unwrap_gitlab_client(client_or_wrapper)
    numeric_id, project_path, encoded_path = normalize_project_input(project_input)

    try:
        if numeric_id is not None:
            project = gl_client.projects.get(numeric_id)
            return ResolvedProject(
                project_id=int(project.id),
                project_path=getattr(project, "path_with_namespace", None),
                encoded_path=None,
                project=project,
            )

        project_data = gl_client.http_get(f"/projects/{encoded_path}")
        resolved_id = int(project_data["id"])
        project = gl_client.projects.get(resolved_id)
        return ResolvedProject(
            project_id=resolved_id,
            project_path=project_path,
            encoded_path=encoded_path,
            project=project,
        )

    except ProjectResolutionError:
        raise
    except Exception as exc:
        raise _classify_resolution_error(exc) from exc


def get_user_projects(client, user_id, username):
    """
    Fetches all projects for a user and classifies them into Personal and Contributed.
    """
    try:
        # Fetch projects where user is a member
        # User request: "GET /projects?membership=true"
        # This catches projects the user has access to (member or owner).

        # We need paginated results for potentially many projects.
        # 1. Fetch direct projects
        projects_data = client._get_paginated(
            f"/users/{user_id}/projects",
            params={"simple": "true"},
            per_page=50,
            max_pages=10
        )

        # 2. Fetch projects from Events (Contribution discovery)
        # This catches projects user pushed to but might not be returned by /projects
        events_data = client._get_paginated(
            f"/users/{user_id}/events",
            params={"action": "pushed"},
            per_page=50,
            max_pages=5
        )

        seen_ids = set()
        unique_projects = []

        for p in projects_data:
            if p['id'] not in seen_ids:
                unique_projects.append(p)
                seen_ids.add(p['id'])

        # Fetch extra projects found in events
        event_project_ids = set()
        for e in events_data:
            pid = e.get('project_id')
            if pid and pid not in seen_ids:
                event_project_ids.add(pid)

        for pid in event_project_ids:
            # Fetch the project object for this ID
            p_extra = client._get(f"/projects/{pid}", params={"simple": "true"})
            if p_extra and isinstance(p_extra, dict) and 'id' in p_extra:
                if p_extra['id'] not in seen_ids:
                    unique_projects.append(p_extra)
                    seen_ids.add(p_extra['id'])

        personal = []
        contributed = []

        for p in unique_projects:
            namespace = p.get('namespace', {})
            ns_path = namespace.get('path')
            ns_kind = namespace.get('kind')

            # Personal if namespace matches username and kind is user
            if ns_kind == 'user' and str(ns_path).lower() == str(username).lower():
                personal.append(p)
            else:
                contributed.append(p)

        return {
            "personal": personal,
            "contributed": contributed,
            "all": unique_projects
        }

    except Exception as e:
        print(f"Error fetching projects: {e}")
        return {"personal": [], "contributed": [], "all": []}
