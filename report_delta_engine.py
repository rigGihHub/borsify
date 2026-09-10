from __future__ import annotations

"""Report Delta Engine 2.0.

Turns the latest earnings release into a compact, point-in-time change map:
reported operating change -> explicit expectation surprise -> post-report analyst
change -> observed price response.  It deliberately creates no investment score.

Only fields that are already available at analysis time are used. Missing consensus
for revenue, margins or cash flow stays missing rather than being inferred from a
headline. Explicit guidance language from fresh news can be used as qualitative
context, but only when the wording itself says guidance/outlook was raised/lowered.
"""

import math
import re
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _text(value: Any) -> str:
    return str(value or "").strip()


def _guidance_signal(catalyst_events: dict[str, Any] | None) -> tuple[int, str]:
    """Return only explicit guidance/outlook changes found in current news titles.

    Generic optimism/pessimism is intentionally ignored. This avoids pretending a
    media headline is structured consensus data.
    """
    events = catalyst_events or {}
    news = events.get("news") if isinstance(events, dict) else None
    if not isinstance(news, list):
        return 0, "Ingen explicit guidningsförändring verifierad"

    positive = re.compile(
        r"\b(raise[sd]?|raised|raises|hike[sd]?|lift(?:s|ed)?|höj(?:er|de|t)|uppjuster(?:ar|ade))\b.*\b(guidance|outlook|forecast|prognos|utsikter)\b|"
        r"\b(guidance|outlook|forecast|prognos|utsikter)\b.*\b(raise[sd]?|raised|raises|hike[sd]?|lift(?:s|ed)?|höj(?:er|de|t)|uppjuster(?:ar|ade))\b",
        re.IGNORECASE,
    )
    negative = re.compile(
        r"\b(cut[sd]?|lower(?:s|ed)?|reduce[sd]?|sänk(?:er|te|t)|nedjuster(?:ar|ade))\b.*\b(guidance|outlook|forecast|prognos|utsikter)\b|"
        r"\b(guidance|outlook|forecast|prognos|utsikter)\b.*\b(cut[sd]?|lower(?:s|ed)?|reduce[sd]?|sänk(?:er|te|t)|nedjuster(?:ar|ade))\b",
        re.IGNORECASE,
    )
    for item in news[:8]:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        if title and negative.search(title):
            return -1, "Explicit sänkt guidning/utsikt i färsk rubrik"
    for item in news[:8]:
        if not isinstance(item, dict):
            continue
        title = _text(item.get("title"))
        if title and positive.search(title):
            return 1, "Explicit höjd guidning/utsikt i färsk rubrik"
    return 0, "Ingen explicit guidningsförändring verifierad"


def build_report_delta(
    inflection_metrics: dict[str, Any] | None,
    post_report: dict[str, Any] | None,
    catalyst_events: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Summarise what materially changed in the latest report.

    Independent evidence families are counted once each. Price response is kept
    separate from the fundamental delta so a muted reaction can be observed rather
    than rewarded as if it were fundamental evidence.
    """
    m = inflection_metrics or {}
    p = post_report or {}

    days = _num(p.get("Post-report dagar sedan"))
    fresh = bool(np.isfinite(days) and 0 <= days <= 45)

    positives: list[str] = []
    negatives: list[str] = []
    observed = 0

    surprise = _num(m.get("Senaste EPS-överraskning"))
    if np.isfinite(surprise):
        observed += 1
        if surprise >= 0.05:
            positives.append(f"EPS slog förväntan med cirka {surprise:.1%}")
        elif surprise <= -0.05:
            negatives.append(f"EPS missade förväntan med cirka {abs(surprise):.1%}")

    rev_yoy = _num(m.get("Omsättning YoY senaste kvartal"))
    rev_acc = _num(m.get("Omsättning acceleration"))
    if np.isfinite(rev_acc):
        observed += 1
        if rev_acc >= 0.03 and (not np.isfinite(rev_yoy) or rev_yoy > 0):
            positives.append("omsättningstillväxten accelererade")
        elif rev_acc <= -0.05:
            negatives.append("omsättningstillväxten bromsade tydligt")

    margin_yoy = _num(m.get("Marginal YoY förändring"))
    margin_qoq = _num(m.get("Marginal QoQ förändring"))
    margin_delta = margin_yoy if np.isfinite(margin_yoy) else margin_qoq
    if np.isfinite(margin_delta):
        observed += 1
        if margin_delta >= 0.015:
            positives.append("marginalen förbättrades tydligt")
        elif margin_delta <= -0.02:
            negatives.append("marginalen försämrades tydligt")

    fcf_yoy = _num(m.get("FCF YoY senaste kvartal"))
    if np.isfinite(fcf_yoy):
        observed += 1
        if fcf_yoy >= 0.15:
            positives.append("fritt kassaflöde förbättrades tydligt")
        elif fcf_yoy <= -0.25:
            negatives.append("fritt kassaflöde försämrades tydligt")

    earnings_yoy = _num(m.get("Vinst YoY senaste kvartal"))
    if np.isfinite(earnings_yoy):
        observed += 1
        if earnings_yoy >= 0.10:
            positives.append("vinsten ökade tydligt")
        elif earnings_yoy <= -0.20:
            negatives.append("vinsten minskade tydligt")

    # Analyst revisions are one expectation family even when both magnitude and
    # breadth are available. Thin coverage remains context and cannot earn support.
    eps_change = _num(m.get("EPS-estimat förändring"))
    revision_balance = _num(m.get("EPS-revisionsbalans"))
    estimate_weight = _num(m.get("Estimat tillförlitlighetsvikt"))
    analyst_usable = np.isfinite(estimate_weight) and estimate_weight >= 0.40
    if analyst_usable and (np.isfinite(eps_change) or np.isfinite(revision_balance)):
        observed += 1
        analyst_pos = ((np.isfinite(eps_change) and eps_change >= 0.02) or
                       (np.isfinite(revision_balance) and revision_balance >= 0.35))
        analyst_neg = ((np.isfinite(eps_change) and eps_change <= -0.02) or
                       (np.isfinite(revision_balance) and revision_balance <= -0.35))
        if analyst_pos and not analyst_neg:
            positives.append("analytikernas vinstprognoser har höjts efter rapporten")
        elif analyst_neg and not analyst_pos:
            negatives.append("analytikernas vinstprognoser har sänkts efter rapporten")

    guidance_dir, guidance_text = _guidance_signal(catalyst_events)
    if guidance_dir:
        observed += 1
        (positives if guidance_dir > 0 else negatives).append(
            "bolaget har höjt guidningen" if guidance_dir > 0 else "bolaget har sänkt guidningen"
        )

    reaction = _num(p.get("Post-report reaktion"))
    drift = _num(p.get("Post-report fortsatt rörelse"))
    muted_reaction = bool(np.isfinite(reaction) and abs(reaction) <= 0.03)
    adverse_reaction = bool(np.isfinite(reaction) and reaction <= -0.05)
    large_reaction = bool(np.isfinite(reaction) and abs(reaction) >= 0.08)

    positive_count = len(positives)
    negative_count = len(negatives)
    broad_positive = fresh and observed >= 4 and positive_count >= 3 and negative_count <= 1
    broad_negative = fresh and observed >= 3 and negative_count >= 2 and negative_count > positive_count

    candidate = bool(broad_positive and not adverse_reaction)
    underreaction = bool(candidate and muted_reaction)

    if not fresh:
        status = "Ingen färsk rapport att jämföra"
        why = "Report Delta används bara när senaste verifierade rapporten är högst cirka 45 dagar gammal."
    elif observed < 3:
        status = "För lite rapportdelta-data"
        why = "För få oberoende rapportmått är verifierade för att Borsify ska dra en bred slutsats."
    elif broad_negative:
        status = "Bred negativ rapportförändring"
        why = "; ".join(negatives[:3]) + "."
    elif broad_positive and adverse_reaction:
        status = "Stark rapport men marknaden säger emot"
        why = "; ".join(positives[:3]) + ". Kursen reagerade samtidigt tydligt negativt, så caset får ingen discovery-fördel."
    elif underreaction:
        status = "Bred positiv rapportförändring · liten kursreaktion"
        why = "; ".join(positives[:3]) + ". Kursreaktionen har hittills varit liten relativt bredden i förbättringen."
    elif broad_positive and large_reaction:
        status = "Bred positiv rapportförändring · stor kursreaktion"
        why = "; ".join(positives[:3]) + ". En stor del kan redan vara inprisad och måste bedömas i djupanalysen."
    elif broad_positive:
        status = "Bred positiv rapportförändring"
        why = "; ".join(positives[:3]) + "."
    elif positive_count > negative_count:
        status = "Övervägande positiv rapportförändring"
        why = "; ".join(positives[:3]) + "." if positives else "Rapportbilden är något bättre men inte tillräckligt bred för discovery-fördel."
    elif negative_count > positive_count:
        status = "Övervägande negativ rapportförändring"
        why = "; ".join(negatives[:3]) + "." if negatives else "Rapportbilden är svagare."
    else:
        status = "Blandad rapportförändring"
        why = "Rapporten innehåller både positiva och negativa förändringar utan tydlig dominans."

    return {
        "Report Delta status": status,
        "Report Delta kandidat": candidate,
        "Report Delta underreaktion": underreaction,
        "Report Delta evidens": int(observed),
        "Report Delta positiva": int(positive_count),
        "Report Delta negativa": int(negative_count),
        "Report Delta styrkor": positives,
        "Report Delta varningar": negatives,
        "Report Delta guidance": guidance_text,
        "Report Delta kursreaktion": reaction,
        "Report Delta fortsatt rörelse": drift,
        "Report Delta förklaring": why,
    }


def select_report_delta_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    """Pick a tiny deterministic report-delta doorway; no aggregate score."""
    if df is None or df.empty or quota <= 0 or "Report Delta kandidat" not in df.columns:
        return []
    work = df[df["Report Delta kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__under"] = work.get("Report Delta underreaktion", False)
    work["__under"] = pd.Series(work["__under"], index=work.index).fillna(False).astype(int)
    work["__pos"] = pd.to_numeric(work.get("Report Delta positiva"), errors="coerce").fillna(-1)
    work["__neg"] = pd.to_numeric(work.get("Report Delta negativa"), errors="coerce").fillna(99)
    work["__evidence"] = pd.to_numeric(work.get("Report Delta evidens"), errors="coerce").fillna(-1)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(
        ["__under", "__pos", "__neg", "__evidence", "__ticker"],
        ascending=[False, False, True, False, True],
        kind="mergesort",
    )
    return [(idx, "Report Delta") for idx in work.head(quota).index]
