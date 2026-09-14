from runtime_diagnostics import clear_runtime_issues, record_runtime_issue, resolve_runtime_issue, runtime_health


def test_runtime_issue_exposes_type_and_impact_not_error_payload():
    state = {}
    issue = record_runtime_issue(state, "recommendation_relevance", RuntimeError("secret payload"), "relevans saknas")
    assert issue["error_type"] == "RuntimeError"
    assert "secret payload" not in str(issue)
    assert runtime_health(state)["status"] == "DEGRADED"


def test_component_is_deduplicated_and_latest_issue_wins():
    state = {}
    record_runtime_issue(state, "ledger", ValueError("first"), "första")
    record_runtime_issue(state, "ledger", TypeError("second"), "andra")
    health = runtime_health(state)
    assert health["count"] == 1
    assert health["issues"][0]["error_type"] == "TypeError"


def test_clear_restores_ok_health():
    state = {}
    record_runtime_issue(state, "outcomes", RuntimeError(), "utfall saknas")
    clear_runtime_issues(state)
    assert runtime_health(state)["status"] == "OK"


def test_success_can_resolve_previous_component_failure():
    state = {}
    record_runtime_issue(state, "ledger", RuntimeError(), "historik saknas")
    resolve_runtime_issue(state, "ledger")
    assert runtime_health(state)["status"] == "OK"


def test_app_records_critical_failures_instead_of_passing():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "4.34.0"' in app
    for component in ["news_event_memory", "recommendation_relevance", "case_plans", "recommendation_outcomes", "missed_winner_history"]:
        assert f'record_runtime_issue(st.session_state, "{component}"' in app
