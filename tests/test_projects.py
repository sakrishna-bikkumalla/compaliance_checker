import pytest

from gitlab_utils.projects import (
    ProjectResolutionError,
    normalize_project_input,
    resolve_project,
)


class _ProjectsAPI:
    def __init__(self, project_obj):
        self._project_obj = project_obj

    def get(self, project_id):
        assert project_id == self._project_obj.id
        return self._project_obj


class _Project:
    def __init__(self, project_id, path):
        self.id = project_id
        self.path_with_namespace = path


class _Client:
    def __init__(self, project_obj):
        self.projects = _ProjectsAPI(project_obj)
        self._project_obj = project_obj

    def http_get(self, endpoint):
        assert endpoint == "/projects/group%2Fsubgroup%2Frepo"
        return {"id": self._project_obj.id}


def test_normalize_project_input_numeric_id():
    pid, path, encoded = normalize_project_input("12345")
    assert pid == 12345
    assert path is None
    assert encoded is None


def test_normalize_project_input_url_strips_git_suffix():
    pid, path, encoded = normalize_project_input("https://gitlab.com/group/subgroup/repo.git")
    assert pid is None
    assert path == "group/subgroup/repo"
    assert encoded == "group%2Fsubgroup%2Frepo"


def test_normalize_project_input_empty_raises():
    with pytest.raises(ProjectResolutionError) as exc:
        normalize_project_input(" ")
    assert exc.value.kind == "invalid_input"


def test_resolve_project_with_path_uses_http_get_then_projects_get():
    project = _Project(42, "group/subgroup/repo")
    resolved = resolve_project(_Client(project), "group/subgroup/repo")

    assert resolved.project_id == 42
    assert resolved.project_path == "group/subgroup/repo"
    assert resolved.encoded_path == "group%2Fsubgroup%2Frepo"
    assert resolved.project.id == 42


def test_resolve_project_classifies_404_as_not_found():
    class NotFoundError(Exception):
        response_code = 404

    class Client404:
        projects = object()

        def http_get(self, _endpoint):
            raise NotFoundError("missing")

    with pytest.raises(ProjectResolutionError) as exc:
        resolve_project(Client404(), "group/repo")

    assert exc.value.kind == "not_found"
