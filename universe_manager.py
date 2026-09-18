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
