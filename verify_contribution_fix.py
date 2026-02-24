import sys


def test_event_discovery_implemented():
    projects_file = "gitlab_utils/projects.py"
    with open(projects_file, "r") as f:
        content = f.read()

    if "/events" in content and '"action": "pushed"' in content:
        print("✅ PASS: Event-based project discovery implemented in projects.py")
    else:
        print("❌ FAIL: Event-based project discovery NOT found in projects.py")
        return False

    if "/projects/{pid}" in content and "p_extra" in content:
        print("✅ PASS: Extra project fetching logic found")
    else:
        print("❌ FAIL: Extra project fetching logic NOT found")
        return False

    return True


if __name__ == "__main__":
    if test_event_discovery_implemented():
        print("\n🎉 Contribution fix verified!")
        sys.exit(0)
    else:
        print("\n❌ Verification failed!")
        sys.exit(1)
