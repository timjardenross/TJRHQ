"""Test helper for dashboard routes behind the SEC-01 shared-secret gate.

Every dashboard route now requires X-Self-Improvement-Secret. Tests that exercise
route behaviour must authenticate; this helper supplies a fixed test-only secret.
It is not a production value and is never read from the environment.
"""

TEST_SI_SECRET = "test-only-si-secret-0123456789abcdef0123456789abcdef"


def si_test_client(dashboard):
    """Return a Flask test client for `dashboard.app` that sends the test secret.

    Sets the module-level secret the gate compares against, for this test process only.
    """
    dashboard._SI_SECRET = TEST_SI_SECRET
    client = dashboard.app.test_client()
    client.environ_base["HTTP_X_SELF_IMPROVEMENT_SECRET"] = TEST_SI_SECRET
    return client
