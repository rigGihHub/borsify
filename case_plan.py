from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text and text not in {"—", "nan", "None"}:
            return text
    return ""


def build_case_plan(case: dict[str, Any] | pd.Series, horizon: str) -> dict[str, Any]:
    """Build a deterministic monitoring plan from already verified Borsify evidence.

    It does not invent price targets, dates, catalysts or probabilities.
    """
    row = case.to_dict() if isinstance(case, pd.Series) else dict(case)
    horizon = str(horizon).lower().strip()

    if horizon == "short":
        thesis = _first_text(
            row.get("Short Why Now"),
            row.get("Catalyst Why Now"),
            "Kortsiktigt case utan tillräckligt tydlig tes.",
        )
        confirmations = []
        if _num(row.get("Short Relative Strength")) >= 65:
            confirmations.append("relativ styrka fortsätter vara tydligt positiv mot jämförelsemarknaden")
        else:
            confirmations.append("relativ styrka förbättras och håller sig positiv mot jämförelsemarknaden")
        if _num(row.get("Short Trend")) >= 70:
            confirmations.append("den positiva trenden håller utan tydligt tekniskt trendbrott")
        else:
            confirmations.append("trendbilden förbättras")
        if _num(row.get("Short Revisions")) >= 65:
            confirmations.append("vinst-/estimatsignalerna fortsätter bekräfta caset")
        elif _num(row.get("Short Revisions")) > 0:
            confirmations.append("vinst-/estimatsignalerna förbättras")
        if _num(row.get("Short Catalyst")) >= 70:
            confirmations.append("den identifierade katalysatorn får fortsatt stöd i verifierad data")

        warning = _first_text(
            row.get("Short Counterargument"),
            row.get("Short Cautions"),
            "relativ styrka eller trend försvagas tydligt",
        )
        breaker = _first_text(row.get("Short Vetoes"))
        if not breaker:
            breaker = (
                "falling-knife-veto, tydligt trendbrott eller annan hård korttidssignal "
                "gör att caset ska omprövas"
            )

        timing = _first_text(row.get("Catalyst Timing"))
        catalyst = _first_text(row.get("Primary Catalyst"))
        if catalyst and catalyst != "Ingen verifierad":
            checkpoint = f"{catalyst}" + (f" · {timing}" if timing else "")
        else:
            checkpoint = "nästa vinst-/estimatuppdatering eller tydlig förändring i trend/relativ styrka"

        return {
            "Case Plan Tes": thesis,
            "Case Plan Bekräftelse": "; ".join(confirmations[:3]),
            "Case Plan Varning": warning,
            "Case Plan Breaker": breaker,
            "Case Plan Nästa kontroll": checkpoint,
            "Case Plan Prisregel": _short_price_rule(row),
            "Case Plan Datastatus": "regelbaserad plan från aktuell Borsify-data",
        }

    thesis = _first_text(
        row.get("Varför marknaden kan ha fel"),
        row.get("Catalyst Why Now"),
        row.get("Varför nu"),
        "Långsiktigt case utan tillräckligt tydlig verifierad tes.",
    )

    confirmations = []
    inflection = _num(row.get("Inflection Score"))
    if inflection >= 65:
        confirmations.append("den positiva förändringsbilden fortsätter eller stärks")
    else:
        confirmations.append("förändringsbilden förbättras i kommande verifierade data")

    mispricing = str(row.get("Mispricing Signal", "") or "")
    if "felprissättning" in mispricing.lower():
        confirmations.append("värderingsgapet består samtidigt som fundamenta håller")
    else:
        confirmations.append("värderingen blir mer attraktiv relativt verifierad fundamental utveckling")

    catalyst = _first_text(row.get("Primary Catalyst"))
    timing = _first_text(row.get("Catalyst Timing"))
    if catalyst and catalyst != "Ingen verifierad":
        confirmations.append(f"{catalyst} börjar ge verifierbart stöd åt tesen")

    warning = _first_text(
        row.get("Devil's Advocate"),
        row.get("Case Neutrals"),
        "fundamenta eller förändringsbilden utvecklas sämre än Base-antagandet",
    )
    breaker = _first_text(row.get("Case Vetoes"))
    if not breaker or breaker == "inga hårda motbevis i gate-modellen":
        breaker = (
            "hög value-trap-risk, otillräcklig datakvalitet eller ett nytt hårt motbevis "
            "i Case Quality Gate gör att rekommendationen ska omprövas"
        )

    if catalyst and catalyst != "Ingen verifierad":
        checkpoint = f"{catalyst}" + (f" · {timing}" if timing else "")
    else:
        report_date = _first_text(row.get("Rapportdatum"))
        checkpoint = (
            f"nästa rapport efter senast verifierade rapportdata {report_date}"
            if report_date else
            "nästa rapport, estimatrevidering eller ny verifierad katalysator"
        )

    return {
        "Case Plan Tes": thesis,
        "Case Plan Bekräftelse": "; ".join(confirmations[:3]),
        "Case Plan Varning": warning,
        "Case Plan Breaker": breaker,
        "Case Plan Nästa kontroll": checkpoint,
        "Case Plan Prisregel": _long_price_rule(row),
        "Case Plan Datastatus": "regelbaserad plan från aktuell Borsify-data",
    }


def _short_price_rule(row: dict[str, Any]) -> str:
    relevance = str(row.get("Relevans nu", "") or "")
    move = _num(row.get("Sedan rekommendation"))
    if relevance == "Mindre attraktivt än vid signal" and np.isfinite(move):
        return (
            f"Kursen är redan {move:+.1%} från tidigare fryst rekommendation utan motsvarande "
            "förstärkning i modellstödet. Risk/reward ska därför omprövas nu."
        )
    if relevance == "Caset har försvagats":
        return "Prisnivån ska inte användas för att försvara caset när modellstödet samtidigt har försvagats."
    return (
        "Ingen godtycklig procentgräns sätts. Om kursen stiger tydligt utan starkare modellstöd "
        "ska värdering och risk/reward omprövas."
    )


def _long_price_rule(row: dict[str, Any]) -> str:
    base_upside = _num(row.get("Base upside"))
    bear_upside = _num(row.get("Bear upside"))
    asym = _num(row.get("Scenario Asymmetry"))
    if np.isfinite(base_upside) and np.isfinite(bear_upside):
        text = (
            f"Nuvarande scenarioarbete visar Base {base_upside:+.0%} och Bear {bear_upside:+.0%} "
            "från den kurs som scenariot bygger på."
        )
        if np.isfinite(asym):
            text += f" Asymmetri {asym:.2f}x."
        return text + " Om dagens kurs ändras väsentligt ska scenariot räknas om – gamla uppsidesiffror får inte återanvändas."
    return (
        "Ingen prisgräns sätts eftersom scenario-/värderingsunderlaget inte räcker för en robust nivå. "
        "Borsify ska hellre säga att underlaget saknas än hitta på en riktkurs."
    )


def apply_case_plans(frame: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    records = {idx: build_case_plan(row, horizon) for idx, row in out.iterrows()}
    plan_frame = pd.DataFrame.from_dict(records, orient="index")
    for col in plan_frame.columns:
        plan_frame[col] = plan_frame[col].astype("object")
    overlap = [c for c in plan_frame.columns if c in out.columns]
    if overlap:
        out = out.drop(columns=overlap)
    return out.join(plan_frame, how="left")
