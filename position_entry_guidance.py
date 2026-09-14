from __future__ import annotations
from typing import Any
import math
import pandas as pd

FULL = "🟢 Köp hela positionen nu"
PARTIAL = "🟡 Börja köpa försiktigt"
WAIT = "🔴 Vänta helt"


def _level(value: Any) -> str:
    return str(value or "").strip().lower()


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else float("nan")
    except Exception:
        return float("nan")


def _initial_size(action: str, company: str, entry: str, risk: float) -> tuple[int, str]:
    """Return share of the user's intended max position, never portfolio percent.

    The sizing is deliberately coarse (0/25/50/100). It is an execution aid derived
    from Borsify's existing company, entry and risk-robustness inputs; it is not a
    personalized portfolio allocation recommendation.
    """
    if action == WAIT:
        return 0, "Ingen ny position innan Borsifys stopporsak har försvunnit."

    if action == FULL:
        if math.isfinite(risk) and risk < 55:
            return 50, "Köpläget är starkt men riskrobustheten är för låg för full startstorlek."
        if math.isfinite(risk) and risk < 65:
            return 50, "Bra bolag och köpläge, men riskrobustheten motiverar en halv första position."
        return 100, "Bolag, köpläge och riskrobusthet stödjer full tänkt maxposition."

    # PARTIAL
    if entry == "orange":
        if math.isfinite(risk) and risk < 55:
            return 25, "Ansträngt köpläge och svagare riskrobusthet: endast en liten första del."
        return 25, "Ansträngt köpläge: börja endast med en liten del och invänta bättre prisstruktur."

    if entry == "yellow":
        if math.isfinite(risk) and risk < 50:
            return 25, "Köpläget är bara okej och riskrobustheten är låg: liten första del."
        return 50, "Caset är köpbar men inte starkt nog för full position direkt."

    # Green entry but only yellow company quality.
    if company == "yellow":
        return 50, "Bra köpläge men bolagskvaliteten motiverar högst en halv första position."

    return 50, "Försiktig startstorlek tills fler delar av caset bekräftas."


def assess_position_entry(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    company = _level(row.get("Bolagsbedömning nivå"))
    entry = _level(row.get("Ingångsläge nivå"))
    better = str(row.get("Bättre ingång", "—") or "—")
    risk = _num(row.get("Risk"))

    if company in {"red"}:
        action = WAIT
        reason = "Bolagsbedömningen är för svag för att motivera en ny position, oavsett pris."
    elif entry == "red":
        action = WAIT
        reason = "Kursen bedöms vara för ansträngd just nu. Borsify vill inte jaga uppgången."
    elif entry == "orange":
        action = PARTIAL if company in {"green"} else WAIT
        reason = (
            "Bolaget är tillräckligt starkt för en försiktig start, men ingångsläget är ansträngt."
            if action == PARTIAL else
            "Både bolags- och ingångsbedömningen är för svaga för att börja köpa nu."
        )
    elif entry == "yellow":
        action = PARTIAL if company in {"green", "yellow"} else WAIT
        reason = (
            "Caset är köpbar men inte tillräckligt starkt för full position direkt."
            if action == PARTIAL else
            "Bolagsbedömningen är för svag för att motivera köp."
        )
    else:  # green entry
        if company == "green":
            action = FULL
            reason = "Både bolagsbedömning och ingångsläge är starka."
        elif company == "yellow":
            action = PARTIAL
            reason = "Ingångsläget är bra men bolagskvaliteten motiverar en mindre första position."
        else:
            action = WAIT
            reason = "Ett bra pris räcker inte när bolagsbedömningen är svag."

    size_pct, size_reason = _initial_size(action, company, entry, risk)
    if action != FULL and better != "—":
        reason += f" Borsify ser en bättre referenszon kring {better}."

    size_label = "0 % · vänta" if size_pct == 0 else f"{size_pct} % av tänkt maxposition"
    return {
        "Positionsråd": action,
        "Positionsråd skäl": reason,
        "Första positionsstorlek %": size_pct,
        "Första positionsstorlek": size_label,
        "Positionsstorlek skäl": size_reason,
    }


def add_position_entry_guidance(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    rows = [assess_position_entry(r) for _, r in out.iterrows()]
    guidance = pd.DataFrame(rows, index=out.index)
    overlap = [c for c in guidance.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(guidance)
