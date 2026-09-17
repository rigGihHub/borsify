from __future__ import annotations

from typing import Any, MutableMapping

# User choices are sticky by design: a checked filter remains active across reruns
# and refreshes until the user explicitly changes it. Do not reset these keys when
# starting a new scan or refreshing market data.
FILTER_DEFAULTS: dict[str, Any] = {
    "filter_dividend_only": False,
}


def ensure_filter_state(state: MutableMapping[str, Any]) -> None:
    """Set defaults only when a choice has never been made."""
    for key, default in FILTER_DEFAULTS.items():
        if key not in state:
            state[key] = default


def dividend_only(state: MutableMapping[str, Any]) -> bool:
    ensure_filter_state(state)
    return bool(state["filter_dividend_only"])


def set_dividend_only(state: MutableMapping[str, Any], enabled: bool) -> None:
    state["filter_dividend_only"] = bool(enabled)


def reset_transient_scan_state(state: MutableMapping[str, Any], keys: list[str]) -> None:
    """Clear scan results without erasing sticky user filters."""
    sticky = set(FILTER_DEFAULTS)
    for key in keys:
        if key not in sticky:
            state.pop(key, None)
