from __future__ import annotations
"""Small, privacy-safe runtime diagnostics for degraded analysis components."""

from datetime import datetime, timezone
from typing import Any, MutableMapping


MAX_RUNTIME_ISSUES = 20


def record_runtime_issue(
    state: MutableMapping[str, Any],
    component: str,
    error: BaseException,
    impact: str,
) -> dict[str, str]:
    """Record failure type and impact without persisting provider payloads."""
    issue = {
        "component": str(component or "unknown"),
        "error_type": type(error).__name__,
        "impact": str(impact or "del av analysen är försvagad"),
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    existing = state.get("bq_runtime_issues", [])
    issues = list(existing) if isinstance(existing, list) else []
    issues = [item for item in issues if isinstance(item, dict) and item.get("component") != issue["component"]]
    issues.append(issue)
    state["bq_runtime_issues"] = issues[-MAX_RUNTIME_ISSUES:]
    return issue


def runtime_health(state: MutableMapping[str, Any]) -> dict[str, Any]:
    issues = state.get("bq_runtime_issues", [])
    valid = [item for item in issues if isinstance(item, dict) and item.get("component")] if isinstance(issues, list) else []
    return {
        "status": "DEGRADED" if valid else "OK",
        "count": len(valid),
        "components": [str(item["component"]) for item in valid],
        "issues": valid,
    }


def clear_runtime_issues(state: MutableMapping[str, Any]) -> None:
    state["bq_runtime_issues"] = []


def resolve_runtime_issue(state: MutableMapping[str, Any], component: str) -> None:
    issues = state.get("bq_runtime_issues", [])
    if not isinstance(issues, list):
        state["bq_runtime_issues"] = []
        return
    state["bq_runtime_issues"] = [
        item for item in issues
        if isinstance(item, dict) and str(item.get("component")) != str(component)
    ]
