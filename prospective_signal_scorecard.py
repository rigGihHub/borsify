from __future__ import annotations

from typing import Any

import pandas as pd

from expectation_gap_validation import validation_table as expectation_gap_validation_table
from literature_signal_validation import SIGNALS, validate_literature_signals
from news_underreaction_validation import validation_table as news_underreaction_validation_table

STATUS_REVIEW = "Behöver granskas"
STATUS_SUPPORT = "Preliminärt stöd"
STATUS_MIXED = "Oklart"
STATUS_WAIT = "Väntar på data"


def _max_int(series: pd.Series | None) -> int:
    if series is None:
        return 0
    values = pd.to_numeric(series, errors="coerce").fillna(0)
    return int(values.max()) if len(values) else 0


def _normalise_validation(name: str, family: str, table: pd.DataFrame, questioned: set[str], supported: set[str]) -> dict[str, Any]:
    if table is None or table.empty:
        return {
            "Hypotes": name, "Familj": family, "Status": STATUS_WAIT,
            "Mogna horisonter": 0, "Största sample": 0,
            "Nästa steg": "Vänta på nya, mogna point-in-time-utfall.",
        }
    statuses = set(table.get("Status", pd.Series(dtype=str)).astype(str))
    mature = table[~table["Status"].astype(str).isin({"För lite prospektiv historik", "Väntar på prospektiva utfall", "För lite historik"})]
    if statuses & questioned:
        status = STATUS_REVIEW
        nxt = "Granska hypotesen manuellt; ingen automatisk modelländring."
    elif statuses & supported:
        status = STATUS_SUPPORT
        nxt = "Samla fler oberoende case och kontrollera om stödet håller över fler horisonter."
    elif not mature.empty:
        status = STATUS_MIXED
        nxt = "Fortsätt samla prospektiva utfall; riktningen är ännu inte tydlig."
    else:
        status = STATUS_WAIT
        nxt = "Vänta på nya, mogna point-in-time-utfall."
    return {
        "Hypotes": name, "Familj": family, "Status": status,
        "Mogna horisonter": int(len(mature)),
        "Största sample": _max_int(table.get("Oberoende case")),
        "Nästa steg": nxt,
    }


def _literature_rows(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizons: tuple[str, ...]) -> list[dict[str, Any]]:
    by_signal: dict[str, list[pd.Series]] = {spec.name: [] for spec in SIGNALS}
    for horizon in horizons:
        table = validate_literature_signals(recommendations, outcomes, horizon)
        if table is None or table.empty:
            continue
        for _, row in table.iterrows():
            by_signal.setdefault(str(row.get("Signal", "—")), []).append(row)

    rows: list[dict[str, Any]] = []
    for spec in SIGNALS:
        signal_rows = by_signal.get(spec.name, [])
        statuses = {str(r.get("Status", "")) for r in signal_rows}
        mature = [r for r in signal_rows if str(r.get("Status", "")) in {"Lovande", "Ifrågasatt", "Oklart"}]
        if "Ifrågasatt" in statuses:
            status, nxt = STATUS_REVIEW, "Granska signalen manuellt innan den får större betydelse."
        elif "Lovande" in statuses:
            status, nxt = STATUS_SUPPORT, "Samla fler oberoende case och kontrollera robusthet över fler horisonter."
        elif mature:
            status, nxt = STATUS_MIXED, "Fortsätt samla frysta framtidsutfall; skillnaden är ännu inte tydlig."
        else:
            status, nxt = STATUS_WAIT, "Vänta på fler mogna point-in-time-utfall."
        samples = [int(pd.to_numeric(pd.Series([r.get("Oberoende case", 0)]), errors="coerce").fillna(0).iloc[0]) for r in signal_rows]
        rows.append({
            "Hypotes": spec.name,
            "Familj": "Litteratursignal",
            "Status": status,
            "Mogna horisonter": len(mature),
            "Största sample": max(samples) if samples else 0,
            "Nästa steg": nxt,
        })
    return rows


def build_prospective_signal_scorecard(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: tuple[str, ...] = ("1m", "3m", "6m"),
) -> pd.DataFrame:
    """Compact governance view of Borsify's newer testable signal hypotheses.

    Descriptive only: this function never changes scores, gates, weights or production policy.
    It intentionally normalises different validation modules into four plain-language states.
    """
    rows: list[dict[str, Any]] = []
    news = news_underreaction_validation_table(recommendations, outcomes, horizons=horizons)
    rows.append(_normalise_validation(
        "News Underreaction", "Förregistrerad signal", news,
        questioned={"Signal ifrågasatt"}, supported={"Prospektivt stöd"},
    ))
    gap = expectation_gap_validation_table(recommendations, outcomes, horizons=horizons)
    rows.append(_normalise_validation(
        "Expectation Gap", "Förregistrerad signal", gap,
        questioned={"Hypotes ifrågasatt"}, supported={"Prospektivt stöd"},
    ))
    rows.extend(_literature_rows(recommendations, outcomes, horizons))

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["Hypotes", "Familj", "Status", "Mogna horisonter", "Största sample", "Nästa steg"])
    order = {STATUS_REVIEW: 0, STATUS_SUPPORT: 1, STATUS_MIXED: 2, STATUS_WAIT: 3}
    out["_order"] = out["Status"].map(order).fillna(9)
    return out.sort_values(["_order", "Hypotes"], kind="stable").drop(columns="_order").reset_index(drop=True)


def scorecard_summary(table: pd.DataFrame) -> dict[str, Any]:
    if table is None or table.empty:
        return {"status": STATUS_WAIT, "text": "Inga signalhypoteser har ännu användbart prospektivt underlag."}
    review = int(table["Status"].eq(STATUS_REVIEW).sum())
    support = int(table["Status"].eq(STATUS_SUPPORT).sum())
    mixed = int(table["Status"].eq(STATUS_MIXED).sum())
    waiting = int(table["Status"].eq(STATUS_WAIT).sum())
    if review:
        return {"status": STATUS_REVIEW, "text": f"{review} hypotes(er) går åt fel håll och bör granskas. Ingen automatisk modelländring görs."}
    if support:
        return {"status": STATUS_SUPPORT, "text": f"{support} hypotes(er) har preliminärt stöd. {mixed} är oklara och {waiting} väntar fortfarande på tillräckligt underlag."}
    if mixed:
        return {"status": STATUS_MIXED, "text": f"{mixed} hypotes(er) har mogna utfall men ingen tydlig riktning ännu. {waiting} väntar fortfarande på mer data."}
    return {"status": STATUS_WAIT, "text": f"Alla {waiting} signalhypoteser väntar fortfarande på tillräckligt många mogna, frysta framtidsutfall."}
