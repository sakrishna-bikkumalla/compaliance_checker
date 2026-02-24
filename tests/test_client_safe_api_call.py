from gitlab_utils.client import safe_api_call


def test_safe_api_call_retries_and_succeeds():
    counter = {"n": 0}

    def flaky():
        counter["n"] += 1
        if counter["n"] < 3:
            raise TimeoutError("transient")
        return ["ok"]

    result = safe_api_call(flaky)
    assert result == ["ok"]
    assert counter["n"] == 3


def test_safe_api_call_non_list_failure_returns_none():
    def always_fails():
        raise ValueError("boom")

    # Intentional quality gate: scalar APIs should return None on unrecoverable failures.
    assert safe_api_call(always_fails) is None
