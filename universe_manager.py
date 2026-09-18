from __future__ import annotations

from typing import Any
import pandas as pd

TARGETS = {
    "Sverige": {"minimum": 500, "goal": 650},
    "Norge": {"minimum": 150, "goal": 250},
    "Danmark": {"minimum": 100, "goal": 150},
}

def universe_health(catalog: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for country, target in TARGETS.items():
        count = int(catalog["Land"].eq(country).sum()) if catalog is not None and not catalog.empty else 0
        rows.append({
            "Land": country,
            "I Borsify": count,
            "Miniminivå": target["minimum"],
            "Målnivå": target["goal"],
            "Saknas till miniminivå": max(0, target["minimum"] - count),
            "Status": "Bra" if count >= target["minimum"] else "Behöver fler aktier",
        })
    return pd.DataFrame(rows)

def nordic_total(catalog: pd.DataFrame) -> dict[str, Any]:
    health = universe_health(catalog)
    return {
        "current": int(health["I Borsify"].sum()),
        "minimum": int(health["Miniminivå"].sum()),
        "goal": int(health["Målnivå"].sum()),
        "missing_to_minimum": int(health["Saknas till miniminivå"].sum()),
    }

def candidate_status(ticker: str, country: str, price_usable: bool, duplicate: bool = False) -> str:
    if duplicate:
        return "Hoppa över – finns redan"
    if country not in TARGETS:
        return "Utanför Norden-prioriteringen"
    if not price_usable:
        return "Karantän – kursdata fungerar inte"
    return "Klar för katalog efter marknads-/handelskontroll"

def validate_candidate_batch(candidates: pd.DataFrame, existing: pd.DataFrame, price_status: dict[str, bool]) -> pd.DataFrame:
    """Prepare discovered listings for catalog admission without trusting discovery alone."""
    if candidates is None or candidates.empty:
        return pd.DataFrame(columns=["Ticker","Land","Nivå","Universe status"])
    known = set(existing.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper()) if existing is not None else set()
    rows = []
    for _, row in candidates.iterrows():
        ticker = str(row.get("Ticker") or "").upper().strip()
        country = str(row.get("Land") or "").strip()
        status = candidate_status(ticker, country, bool(price_status.get(ticker)), ticker in known)
        rec = row.to_dict()
        rec["Ticker"] = ticker
        rec["Universe status"] = status
        rec["Kursdata fungerar"] = bool(price_status.get(ticker))
        rows.append(rec)
    return pd.DataFrame(rows)

def admission_ready(candidates: pd.DataFrame) -> pd.DataFrame:
    """Only candidates with usable quote history move forward; tradability is checked separately."""
    if candidates is None or candidates.empty or "Universe status" not in candidates.columns:
        return pd.DataFrame(columns=candidates.columns if isinstance(candidates, pd.DataFrame) else [])
    return candidates[candidates["Universe status"].eq("Klar för katalog efter marknads-/handelskontroll")].copy()
