import sys
import types


def _install_streamlit_stub() -> None:
    if "streamlit" in sys.modules:
        return

    st = types.ModuleType("streamlit")
    st.session_state = {}

    def _noop(*_args, **_kwargs):
        return None

    st.error = _noop
    st.warning = _noop
    st.info = _noop
    st.success = _noop
    st.caption = _noop
    st.markdown = _noop
    st.divider = _noop
    st.rerun = _noop
    sys.modules["streamlit"] = st


def _install_pandas_stub() -> None:
    if "pandas" in sys.modules:
        return

    pd = types.ModuleType("pandas")

    class _DummyDataFrame:
        def __init__(self, *_args, **_kwargs):
            pass

        def sort_values(self, *_args, **_kwargs):
            return self

        def to_excel(self, *_args, **_kwargs):
            return None

    class _DummyWriter:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, _exc_type, _exc, _tb):
            return False

    pd.DataFrame = _DummyDataFrame
    pd.ExcelWriter = _DummyWriter
    sys.modules["pandas"] = pd


def _install_gitlab_stub() -> None:
    if "gitlab" in sys.modules:
        return

    gitlab = types.ModuleType("gitlab")

    class _Gitlab:
        def __init__(self, *args, **kwargs):
            pass

        def auth(self):
            return None

    class _GitlabAuthenticationError(Exception):
        pass

    class _GitlabConnectionError(Exception):
        pass

    gitlab.Gitlab = _Gitlab
    gitlab.exceptions = types.SimpleNamespace(
        GitlabAuthenticationError=_GitlabAuthenticationError,
        GitlabConnectionError=_GitlabConnectionError,
    )
    sys.modules["gitlab"] = gitlab


_install_streamlit_stub()
_install_pandas_stub()
_install_gitlab_stub()
