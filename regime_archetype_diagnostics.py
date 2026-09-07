from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from interaction_diagnostics import ARCHETYPES, prepare_interaction_sample, _outcome_basis

MIN_REGIME_TOTAL = 14
MIN_BOTH = 4
MIN_SINGLE = 5
MIN_MATURE_REGIMES = 2
POSSIBLE_GAP = 0.04
STRONG_GAP = 0.08
MIN_HIT_DELTA = 0.10
REGIME_DIVERGENCE = 0.08


def _regime_name(value: Any) -> str:
    text = str(value or "").strip()
    return text if text else ""


def _classify(oriented_gap: float, oriented_hit_delta: float) -> str:
    if not math.isfinite(oriented_gap):
        return "För lite underlag"
    if oriented_gap >= STRONG_GAP and oriented_hit_delta >= MIN_HIT_DELTA:
        return "Stark möjlig interaction"
    if oriented_gap >= POSSIBLE_GAP and oriented_hit_delta >= 0:
        return "Möjlig interaction"
    if oriented_gap <= -POSSIBLE_GAP:
        return "Motsäger hypotesen"
    return "Ingen tydlig interaction"


def regime_archetype_table(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizon: str = "1m",
    horizon_type: str = "short",
) -> pd.DataFrame:
    """Evaluate pre-defined archetypes separately inside frozen market regimes.

    A regime is only evaluated when it has enough independent observations and enough
    observations in both the two-leg group and the exactly-one-leg comparison group.
    This is a descriptive robustness check. It does not infer causality or alter model rules.
    """
    cols = [
        "Arketyp", "Marknadsläge", "Riktning", "Status", "Båda signaler", "En signal",
        "Median båda", "Median en", "Interaktionsgap", "Träffskillnad", "Utfallsmått",
    ]
    data = prepare_interaction_sample(recommendations, outcomes, horizon, horizon_type)
    if data.empty or "_snap" not in data.columns:
        return pd.DataFrame(columns=cols)
    data = data.copy()
    data["_regime"] = data["_snap"].map(lambda s: _regime_name(s.get("Marknadsläge")))
    data = data[data["_regime"].ne("")].copy()
    if data.empty:
        return pd.DataFrame(columns=cols)

    metric, metric_label = _outcome_basis(data)
    specs = [s for s in ARCHETYPES if s.model == str(horizon_type).strip().lower()]
    rows: list[dict[str, Any]] = []
    for regime, group in data.groupby("_regime", sort=True):
        if len(group) < MIN_REGIME_TOTAL:
            continue
        for spec in specs:
            a = group["_snap"].map(spec.leg_a).astype(bool)
            b = group["_snap"].map(spec.leg_b).astype(bool)
            both_vals = pd.to_numeric(group.loc[a & b, metric], errors="coerce").dropna()
            single_vals = pd.to_numeric(group.loc[a ^ b, metric], errors="coerce").dropna()
            if len(both_vals) < MIN_BOTH or len(single_vals) < MIN_SINGLE:
                continue
            med_both = float(both_vals.median())
            med_single = float(single_vals.median())
            raw_gap = med_both - med_single
            hit_both = float((both_vals > 0).mean())
            hit_single = float((single_vals > 0).mean())
            raw_hit_delta = hit_both - hit_single
            oriented_gap = raw_gap * spec.expected
            oriented_hit_delta = raw_hit_delta * spec.expected
            rows.append({
                "Arketyp": spec.name,
                "Marknadsläge": regime,
                "Riktning": "Positiv kombination" if spec.expected > 0 else "Riskkombination",
                "Status": _classify(oriented_gap, oriented_hit_delta),
                "Båda signaler": int(len(both_vals)),
                "En signal": int(len(single_vals)),
                "Median båda": f"{med_both*100:.1f}%",
                "Median en": f"{med_single*100:.1f}%",
                "Interaktionsgap": f"{raw_gap*100:.1f} pp",
                "Träffskillnad": f"{raw_hit_delta*100:.1f} pp",
                "Utfallsmått": metric_label,
                "_oriented_gap": oriented_gap,
            })
    if not rows:
        return pd.DataFrame(columns=cols)
    return (pd.DataFrame(rows)
            .sort_values(["Arketyp", "Marknadsläge"], kind="stable")
            .drop(columns=["_oriented_gap"])
            .reset_index(drop=True))


def regime_archetype_consistency(table: pd.DataFrame) -> pd.DataFrame:
    """Summarize whether each archetype is robust or regime-dependent."""
    cols = ["Arketyp", "Mogna marknadslägen", "Bedömning", "Tolkning"]
    if table is None or table.empty:
        return pd.DataFrame(columns=cols)

    rows: list[dict[str, str | int]] = []
    for name, group in table.groupby("Arketyp", sort=True):
        if len(group) < MIN_MATURE_REGIMES:
            continue
        statuses = group["Status"].astype(str).tolist()
        positive = sum(s in {"Stark möjlig interaction", "Möjlig interaction"} for s in statuses)
        negative = sum(s == "Motsäger hypotesen" for s in statuses)

        # Parse displayed percentage-point gaps back only for a simple cross-regime spread.
        gaps = []
        for x in group["Interaktionsgap"].astype(str):
            try:
                gaps.append(float(x.replace(" pp", "")) / 100.0)
            except Exception:
                pass
        spread = (max(gaps) - min(gaps)) if gaps else np.nan

        if positive and negative:
            assessment = "Regimberoende"
            text = "Kombinationen ser hjälpsam ut i minst ett marknadsläge men motsäger hypotesen i ett annat. Behandla den inte som generell regel."
        elif positive >= 2 and negative == 0:
            assessment = "Robust positiv"
            text = "Kombinationen har positivt stöd i minst två mogna marknadslägen och inget tydligt motsägande läge. Fortsatt validering krävs."
        elif negative >= 2 and positive == 0:
            assessment = "Robust ifrågasatt"
            text = "Hypotesen motsägs i minst två mogna marknadslägen. Granska om kombinationen ska nedtonas, men ändra inget automatiskt."
        elif math.isfinite(spread) and spread >= REGIME_DIVERGENCE:
            assessment = "Möjligen regimkänslig"
            text = "Interaktionsgapet varierar tydligt mellan marknadslägen även om riktningen inte byter tecken."
        else:
            assessment = "Ingen tydlig regimskillnad"
            text = "Tillräckliga regimdata finns, men ingen stark skillnad mellan marknadslägen syns ännu."
        rows.append({
            "Arketyp": name,
            "Mogna marknadslägen": int(len(group)),
            "Bedömning": assessment,
            "Tolkning": text,
        })
    return pd.DataFrame(rows, columns=cols)


def regime_archetype_summary(detail: pd.DataFrame, consistency: pd.DataFrame) -> dict[str, str]:
    if detail is None or detail.empty:
        return {"status": "Vänta", "text": "För lite fryst marknadslägesdata för att testa signalarketyper per regim."}
    if consistency is None or consistency.empty:
        return {"status": "Vänta", "text": "Minst två marknadslägen med moget underlag krävs innan Borsify bedömer regimberoende."}
    regime_dependent = int(consistency["Bedömning"].isin(["Regimberoende", "Möjligen regimkänslig"]).sum())
    robust_pos = int((consistency["Bedömning"] == "Robust positiv").sum())
    robust_bad = int((consistency["Bedömning"] == "Robust ifrågasatt").sum())
    if regime_dependent:
        return {"status": "Regimskillnader hittade", "text": f"{regime_dependent} arketyp(er) verkar bero på marknadsläget. Använd dem inte som generella regler utan fortsatt granskning."}
    if robust_bad:
        return {"status": "Hypoteser ifrågasatta", "text": f"{robust_bad} arketyp(er) motsägs i flera marknadslägen. Det är en granskningssignal, inte ett automatiskt modellbeslut."}
    if robust_pos:
        return {"status": "Robust stöd hittat", "text": f"{robust_pos} arketyp(er) har positivt stöd i flera marknadslägen. Det stärker robustheten men bevisar inte kausalitet."}
    return {"status": "Ingen tydlig regimskillnad", "text": "Mogna regimdata finns, men inga tydliga skillnader mellan marknadslägen står ut ännu."}
