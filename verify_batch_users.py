import sys


def test_ssl_verify_disabled():
    client_file = "gitlab_utils/client.py"
    with open(client_file, "r") as f:
        content = f.read()

    if "ssl_verify=False" in content:
        print("✅ PASS: ssl_verify is set to False in client.py")
        return True
    else:
        print("❌ FAIL: ssl_verify is NOT set to False in client.py")
        return False


def test_default_users_exist():
    batch_file = "modes/batch_mode.py"
    with open(batch_file, "r") as f:
        content = f.read()

    passed = True
    if "DEFAULT_ICFAI_USERS =" in content and "saikrishna_b" in content:
        print("✅ PASS: DEFAULT_ICFAI_USERS is defined with users")
    else:
        print("❌ FAIL: DEFAULT_ICFAI_USERS is missing or empty")
        passed = False

    if "DEFAULT_RCTS_USERS =" in content and "vai5h" in content:
        print("✅ PASS: DEFAULT_RCTS_USERS is defined with users")
    else:
        print("❌ FAIL: DEFAULT_RCTS_USERS is missing or empty")
        passed = False

    if "value=default_value" in content:
        print("✅ PASS: st.text_area uses default_value")
    else:
        print("❌ FAIL: st.text_area does not use default_value")
        passed = False

    return passed


if __name__ == "__main__":
    s1 = test_ssl_verify_disabled()
    s2 = test_default_users_exist()
    if s1 and s2:
        print("\n🎉 All verification checks passed!")
        sys.exit(0)
    else:
        print("\n❌ Verification failed!")
        sys.exit(1)
