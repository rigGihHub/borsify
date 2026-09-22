from __future__ import annotations

from typing import Any, MutableMapping

# User choices are sticky by design: a checked filter remains active across reruns
# and refreshes until the user explicitly changes it. Do not reset these keys when
# starting a new scan or refreshing market data.
FILTER_DEFAULTS: dict[str, Any] = {
    "filter_dividend_only": False,
    "filter_country": "Alla",
    "filter_max_price": None,
    "filter_intent": "Bästa möjligheter just nu",
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


def sticky_widget_key(name: str) -> str:
    """Stable Streamlit key: reruns keep the user choice until they change it."""
    return f"borsify_sticky_{name}"


def copy_widget_choice(state: MutableMapping[str, Any], widget_key: str, filter_key: str) -> None:
    """Copy an explicit UI change into persistent filter state; never reset implicitly."""
    if widget_key in state:
        state[filter_key] = state[widget_key]
