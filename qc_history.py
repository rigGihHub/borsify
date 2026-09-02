from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import Any
import math
import pandas as pd

FAILURE_THRESHOLD = 3
QUARANTINE_DAYS = 7

def _iso_now(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")

def _parse(value: Any) -> datetime | None:
    if value in (None, "", "—"):
        return None
    try:
        ts = pd.to_datetime(value, utc=True, errors="coerce")
        if pd.isna(ts):
            return None
        return ts.to_pydatetime()
    except Exception:
        return None

def is_quarantined(state: dict[str, Any] | pd.Series | None, now: datetime | None = None) -> bool:
    if state is None:
        return False
    data = state.to_dict() if isinstance(state, pd.Series) else dict(state)
    until = _parse(data.get("quarantine_until"))
    if until is None:
        return False
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc) < until

def evolve_qc_state(
    previous: dict[str, Any] | pd.Series | None,
    *,
    symbol: str,
    outcome: str,
    reason: str = "",
    now: datetime | None = None,
    count_failure: bool = True,
) -> dict[str, Any]:
    """Update persistent QC state deterministically.

    outcomes:
      verified / partial -> usable market data, reset hard-failure streak.
      hard_failure -> strike, quarantine after repeated failures.
      transient_failure -> logged but does not increase strike.
    """
    prev = previous.to_dict() if isinstance(previous, pd.Series) else dict(previous or {})
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    streak = int(prev.get("failure_streak") or 0)
    total_success = int(prev.get("success_count") or 0)
    total_failure = int(prev.get("failure_count") or 0)
    last_verified = prev.get("last_verified_at")
    quarantine_until = prev.get("quarantine_until")

    if outcome in {"verified", "partial"}:
        streak = 0
        total_success += 1
        last_verified = _iso_now(current)
        quarantine_until = None
        status = "VERIFIERAD" if outcome == "verified" else "DELVIS VERIFIERAD"
    elif outcome == "hard_failure":
        if count_failure:
            streak += 1
            total_failure += 1
        status = "MISSLYCKAD"
        if count_failure and streak >= FAILURE_THRESHOLD:
            quarantine_until = _iso_now(current + timedelta(days=QUARANTINE_DAYS))
            status = "KARANTÄN"
    else:
        status = str(prev.get("status") or "OKÄND")
        # A probable provider-wide/transient error must not poison the ticker state.
        if outcome == "transient_failure":
            reason = reason or "tillfälligt datakällefel – ingen QC-strike"

    return {
        "symbol": str(symbol).upper().strip(),
        "status": status,
        "failure_streak": streak,
        "success_count": total_success,
        "failure_count": total_failure,
        "last_checked_at": _iso_now(current),
        "last_verified_at": last_verified,
        "last_reason": str(reason or ""),
        "quarantine_until": quarantine_until,
    }

def scan_health(success_count: int, attempted_count: int) -> dict[str, Any]:
    attempted=max(0,int(attempted_count))
    success=max(0,int(success_count))
    ratio=(success/attempted) if attempted else 1.0
    # Prevent a Yahoo/provider outage from quarantining hundreds of healthy tickers.
    healthy = attempted == 0 or success >= 3 or ratio >= 0.20
    return {"success_ratio":ratio, "provider_healthy_enough":healthy}

def quarantine_summary(states: pd.DataFrame, now: datetime | None = None) -> dict[str,int]:
    if states is None or states.empty:
        return {"quarantined":0,"failing":0,"verified":0,"partial":0,"total":0}
    qs=states.apply(lambda r: is_quarantined(r,now),axis=1)
    return {
        "quarantined":int(qs.sum()),
        "failing":int((pd.to_numeric(states.get("failure_streak",0),errors="coerce").fillna(0)>0).sum()),
        "verified":int((states.get("status",pd.Series(dtype=str))=="VERIFIERAD").sum()),
        "partial":int((states.get("status",pd.Series(dtype=str))=="DELVIS VERIFIERAD").sum()),
        "total":int(len(states)),
    }


def should_record_qc_outcome(
    previous: dict[str, Any] | pd.Series | None,
    outcome: str,
    now: datetime | None = None,
) -> bool:
    """Avoid treating Streamlit reruns as independent QC observations.

    The same effective outcome is persisted at most once per UTC day. A changed
    outcome (for example failure -> verified) is recorded immediately.
    """
    if previous is None:
        return True
    prev = previous.to_dict() if isinstance(previous, pd.Series) else dict(previous)
    checked = _parse(prev.get("last_checked_at"))
    if checked is None:
        return True
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if checked.date() != current.date():
        return True
    expected = {
        "verified": "VERIFIERAD",
        "partial": "DELVIS VERIFIERAD",
        "hard_failure": "MISSLYCKAD",
    }.get(outcome)
    # KARANTÄN is also the persisted form of repeated hard failures.
    if outcome == "hard_failure" and str(prev.get("status")) == "KARANTÄN":
        expected = "KARANTÄN"
    return str(prev.get("status") or "") != str(expected or prev.get("status") or "")
