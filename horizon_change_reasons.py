from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


SNAPSHOT_FIELDS = {
    "Värdering": "valuation",
    "Kvalitet": "quality",
    "Marknadsläge": "setup",
    "Risk": "risk",
    "Datatäckning": "coverage",
}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def snapshot_details(row: pd.Series | dict[str, Any]) -> dict[str, float | str | bool | None]:
    """Freeze only fields known at ranking time and useful for later explanation."""
    details: dict[str, float | str | bool | None] = {}
    for current_name, frozen_name in SNAPSHOT_FIELDS.items():
        value = _num(row.get(current_name))
        details[frozen_name] = round(value, 6) if np.isfinite(value) else None
    relative = _num(row.get("Relativ styrka"))
    readiness = _num(row.get("Case Readiness"))
    details["relative_strength"] = round(relative, 6) if np.isfinite(relative) else None
    details["case_readiness"] = round(readiness, 6) if np.isfinite(readiness) else None
    details["overextended"] = bool(row.get("För långt gången") is True)
    details["signal"] = str(row.get("Signal") or "")
    return details


def _delta_reason(label: str, delta: float) -> tuple[str, str] | None:
    """Return (direction, plain-language reason) for a material frozen change."""
    thresholds = {"Värdering": 3.0, "Kvalitet": 3.0, "Marknadsläge": 4.0, "Risk": 3.0, "Datatäckning": 0.06,
                  "Relativ styrka": 5.0, "Case Readiness": 4.0}
    threshold = thresholds[label]
    if abs(delta) < threshold:
        return None
    positive = delta > 0
    wording = {
        "Värdering": ("värderingen har blivit mer attraktiv", "värderingen har blivit mindre attraktiv"),
        "Kvalitet": ("bolagskvaliteten har stärkts", "bolagskvaliteten har försvagats"),
        "Marknadsläge": ("marknadsläget och timingen har förbättrats", "marknadsläget och timingen har försämrats"),
        "Risk": ("riskprofilen har förbättrats", "riskprofilen har försämrats"),
        "Datatäckning": ("underlaget har blivit bättre", "underlaget har blivit tunnare"),
        "Relativ styrka": ("aktien går tydligare bättre än marknaden", "aktien går svagare jämfört med marknaden"),
        "Case Readiness": ("caset är bättre underbyggt", "caset är mindre väl underbyggt"),
    }
    return ("positive" if positive else "negative", wording[label][0 if positive else 1])


def explain_change(current: pd.Series | dict[str, Any], previous: pd.Series | dict[str, Any] | None, change_label: str) -> str:
    """Explain a change signal from frozen point-in-time inputs.

    No missing historical component is reconstructed from current data. If v3.44
    history does not yet exist, the function explicitly says so.
    """
    label = str(change_label or "")
    if previous is None:
        return "Första jämförbara observationen i den här listan."

    pairs = [
        ("Värdering", "Värdering", "valuation"),
        ("Kvalitet", "Kvalitet", "quality"),
        ("Marknadsläge", "Marknadsläge", "setup"),
        ("Risk", "Risk", "risk"),
        ("Datatäckning", "Datatäckning", "coverage"),
        ("Relativ styrka", "Relativ styrka", "relative_strength"),
        ("Case Readiness", "Case Readiness", "case_readiness"),
    ]
    reasons: list[tuple[str, float, str]] = []
    any_comparable = False
    for display, current_key, previous_key in pairs:
        now = _num(current.get(current_key)); old = _num(previous.get(previous_key))
        if not (np.isfinite(now) and np.isfinite(old)):
            continue
        any_comparable = True
        delta = now - old
        result = _delta_reason(display, delta)
        if result:
            direction, text = result
            reasons.append((direction, abs(delta), text))

    previous_overextended = previous.get("overextended")
    current_overextended = bool(current.get("För långt gången") is True)
    if previous_overextended is not None and bool(previous_overextended) != current_overextended:
        any_comparable = True
        if current_overextended:
            reasons.append(("negative", 99.0, "kursen har gått för långt för ett färskt köp"))
        else:
            reasons.append(("positive", 99.0, "kursen är inte längre lika utsträckt"))

    if not any_comparable:
        return "Detaljerad jämförelse börjar byggas från v3.44; äldre analys saknar frysta delkomponenter."

    wanted = "positive" if label == "STÄRKT" else "negative" if label == "FÖRSVAGAD" else None
    selected = [x for x in reasons if wanted is None or x[0] == wanted]
    if not selected and reasons:
        selected = reasons
    selected = sorted(selected, key=lambda x: x[1], reverse=True)[:2]
    if selected:
        return "; ".join(x[2] for x in selected) + "."

    if label == "OFÖRÄNDRAD":
        return "Inga stora förändringar i värdering, kvalitet, risk, timing eller underlag."
    if label in {"NY KÖPSIGNAL", "NY PÅ LISTAN"}:
        return "Ny på listan; jämförbar förändringshistorik byggs från och med dagens analys."
    return "Förändringen kommer främst från rankingen eller totalpoängen; ingen enskild delkomponent ändrades tillräckligt mycket."


def add_change_reasons(current: pd.DataFrame, previous: pd.DataFrame, horizon: str = "") -> pd.DataFrame:
    if current is None or current.empty:
        return current.copy() if isinstance(current, pd.DataFrame) else pd.DataFrame()
    out = current.copy()
    prev_map: dict[str, dict[str, Any]] = {}
    if isinstance(previous, pd.DataFrame) and not previous.empty:
        for _, row in previous.iterrows():
            symbol = str(row.get("Ticker") or "").upper().strip()
            if symbol:
                prev_map[symbol] = row.to_dict()
    out["Vad har förändrats"] = [
        explain_change(row, prev_map.get(str(row.get("Ticker") or "").upper().strip()), str(row.get("Förändring") or ""))
        for _, row in out.iterrows()
    ]
    return out
