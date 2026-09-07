from __future__ import annotations

from typing import Any
import pandas as pd

from signal_governance import build_signal_governance
from prospective_challenger_registry import prospective_challenger_results, prospective_governance
from prospective_policy_registry import prospective_policy_results, prospective_policy_governance
from policy_promotion_protocol import policy_promotion_protocol

LEVEL_HYPOTHESIS = "1 · Hypotes"
LEVEL_HISTORICAL = "2 · Historiskt stöd"
LEVEL_PROSPECTIVE = "3 · Prospektiv evidens"
LEVEL_REVIEW = "4 · Redo för manuell granskning"
LEVEL_PRODUCTION = "5 · Produktion · följs upp"


def _signal_rows(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> list[dict[str, Any]]:
    table = build_signal_governance(recommendations, outcomes)
    rows: list[dict[str, Any]] = []
    for _, r in table.iterrows():
        action = str(r.get("Åtgärd", ""))
        evaluated = int(r.get("Utvärderade horisonter", 0) or 0)
        # These signals are already production inputs. Maturity describes evidence,
        # not whether the code is active; avoid implying that historical validation
        # retroactively made them production-ready.
        if evaluated <= 0:
            level = LEVEL_HYPOTHESIS
        elif action in {"Behåll – stöd i historiken", "Behåll under bevakning"}:
            level = LEVEL_HISTORICAL
        else:
            level = LEVEL_HISTORICAL
        rows.append({
            "Typ": "Signal",
            "Namn": str(r.get("Signal", "—")),
            "Evidensnivå": level,
            "Status": action or "Vänta",
            "Mogna horisonter": evaluated,
            "Största sample": int(r.get("Största oberoende sample", 0) or 0),
            "Nästa krav": "Prospektiv evidens över fler nya case; ingen automatisk viktändring.",
        })
    return rows


def _challenger_rows(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> list[dict[str, Any]]:
    detail = prospective_challenger_results(recommendations, outcomes)
    table = prospective_governance(detail)
    rows: list[dict[str, Any]] = []
    for _, r in table.iterrows():
        status = str(r.get("Status", ""))
        evaluated = int(r.get("Utvärderade horisonter", 0) or 0)
        if "Kandidat" in status:
            level = LEVEL_REVIEW
            nxt = "Manuell promotionsgranskning; ingen automatisk champion-ändring."
        elif evaluated > 0:
            level = LEVEL_PROSPECTIVE
            nxt = "Fler förregistrerade, oberoende och mogna utfall."
        else:
            level = LEVEL_HYPOTHESIS
            nxt = "Vänta på utfall från case skapade efter förregistreringen."
        rows.append({
            "Typ": "Challenger", "Namn": str(r.get("Challenger", "—")),
            "Evidensnivå": level, "Status": status or "Vänta",
            "Mogna horisonter": evaluated,
            "Största sample": int(r.get("Största oberoende sample", 0) or 0),
            "Nästa krav": nxt,
        })
    return rows


def _policy_rows(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> list[dict[str, Any]]:
    detail = prospective_policy_results(recommendations, outcomes, ["1m", "3m", "6m"], "short")
    table = prospective_policy_governance(detail)
    promotion, _ = policy_promotion_protocol(recommendations, outcomes)
    promo_by_name = {}
    if promotion is not None and not promotion.empty:
        name_col = "Policy" if "Policy" in promotion.columns else "Namn" if "Namn" in promotion.columns else None
        if name_col:
            promo_by_name = {str(r[name_col]): str(r.get("Status", "")) for _, r in promotion.iterrows()}
    rows: list[dict[str, Any]] = []
    for _, r in table.iterrows():
        name = str(r.get("Policy", r.get("Namn", "—")))
        status = str(r.get("Status", ""))
        evaluated = int(r.get("Utvärderade horisonter", 0) or 0)
        promo = promo_by_name.get(name, "")
        if "Redo" in promo or "promotion" in promo.lower() and "redo" in promo.lower():
            level, nxt = LEVEL_REVIEW, "Dokumenterat manuellt releasebeslut och runtime-fingerprint."
        elif "Kandidat" in status:
            level, nxt = LEVEL_REVIEW, "Klara promotion-protokollets fem grindar."
        elif evaluated > 0:
            level, nxt = LEVEL_PROSPECTIVE, "Fler förregistrerade target-case och mogna utfall."
        else:
            level, nxt = LEVEL_HYPOTHESIS, "Vänta på case efter policyförregistreringen."
        rows.append({
            "Typ": "Policy", "Namn": name, "Evidensnivå": level,
            "Status": promo or status or "Vänta", "Mogna horisonter": evaluated,
            "Största sample": int(r.get("Största oberoende sample", 0) or 0), "Nästa krav": nxt,
        })
    return rows


def build_evidence_maturity_dashboard(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """One conservative view of evidence maturity across signals, challengers and policies.

    The dashboard is descriptive only. It never changes scores, gates, weights,
    champion models, policies or production state.
    """
    rows = _signal_rows(recommendations, outcomes) + _challenger_rows(recommendations, outcomes) + _policy_rows(recommendations, outcomes)
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["Typ", "Namn", "Evidensnivå", "Status", "Mogna horisonter", "Största sample", "Nästa krav"])
    order = {LEVEL_REVIEW: 0, LEVEL_PROSPECTIVE: 1, LEVEL_HISTORICAL: 2, LEVEL_HYPOTHESIS: 3, LEVEL_PRODUCTION: 4}
    out["_order"] = out["Evidensnivå"].map(order).fillna(9)
    return out.sort_values(["_order", "Typ", "Namn"], kind="stable").drop(columns="_order").reset_index(drop=True)


def evidence_maturity_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": "Vänta", "text": "Ingen mogen evidens finns ännu.", "review_ready": 0, "prospective": 0}
    review = int(table["Evidensnivå"].eq(LEVEL_REVIEW).sum())
    prospective = int(table["Evidensnivå"].eq(LEVEL_PROSPECTIVE).sum())
    historical = int(table["Evidensnivå"].eq(LEVEL_HISTORICAL).sum())
    if review:
        text = f"{review} hypotes(er) har nått manuell granskningsnivå. Det är inte samma sak som godkänd produktionsändring."
        status = "Granska"
    elif prospective:
        text = f"{prospective} hypotes(er) har prospektiv evidens men behöver mer mogen historik innan beslut."
        status = "Prospektiv"
    elif historical:
        text = f"{historical} signal(er) har historiskt valideringsunderlag, men det ersätter inte prospektiv bekräftelse."
        status = "Historisk"
    else:
        text, status = "Registrerade hypoteser väntar fortfarande på mogna, orörda utfall.", "Vänta"
    return {"status": status, "text": text, "review_ready": review, "prospective": prospective}
