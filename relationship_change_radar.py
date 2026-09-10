from __future__ import annotations

"""Relationship Materiality & Change Radar.

Separates a static verified company relationship from a *recently changed* relationship.
The layer is intentionally score-free and conservative: financial materiality is never
invented. A relationship-change candidate needs explicit source-backed change metadata,
a recent enough event, its own fundamental support, and no strong fresh contradiction.
"""

from datetime import date, datetime
from typing import Any
import math
import pandas as pd

CHANGE_TYPES = {
    "new_contract",
    "contract_extension",
    "volume_expansion",
    "capacity_expansion",
    "new_customer",
    "new_supplier",
    "strategic_expansion",
    "collaboration_confirmation",
    "other_change",
}
MATERIALITY_LEVELS = {"unknown", "qualitative", "multiyear", "quantified_scope", "financially_quantified"}
MATERIALITY_PRIORITY = {
    "unknown": 0,
    "qualitative": 1,
    "multiyear": 2,
    "quantified_scope": 3,
    "financially_quantified": 4,
}


def _text(v: Any) -> str:
    return str(v or "").strip()


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else float("nan")
    except Exception:
        return float("nan")


def _bool(v: Any) -> bool:
    try:
        if pd.isna(v):
            return False
    except Exception:
        pass
    if isinstance(v, str):
        return v.strip().casefold() in {"1", "true", "yes", "ja", "active"}
    return bool(v)


def _iso(v: Any) -> date | None:
    s = _text(v)
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def add_relationship_change_radar(
    df: pd.DataFrame,
    relationships: pd.DataFrame,
    *,
    as_of: str | date = "2026-09-09",
    recent_days: int = 365,
    fresh_days: int = 120,
) -> pd.DataFrame:
    """Attach explicit relationship-change evidence to target companies.

    Only registry rows with valid change_type/change_date/materiality_level are used.
    `materiality_level` describes the *quality of disclosed scope evidence*, not an
    inferred earnings contribution. Financial materiality must be explicitly sourced.
    """
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    defaults = {
        "Relationsförändring status": "Ingen verifierad relationsförändring",
        "Relationsförändring kandidat": False,
        "Relationsförändring stark": False,
        "Relationsförändring typ": "",
        "Relationsförändring datum": "",
        "Relationsförändring ålder dagar": float("nan"),
        "Relationsförändring materialitet": "unknown",
        "Relationsförändring materialitet evidens": "",
        "Relationsförändring källbolag": "",
        "Relationsförändring evidens": "",
        "Relationsförändring källa": "",
        "Relationsförändring förklaring": "",
    }
    for c, v in defaults.items():
        out[c] = v
    if out.empty or relationships is None or relationships.empty:
        return out

    required = {"source_ticker", "target_ticker", "relationship_type", "direction", "source_url", "active", "change_type", "change_date", "materiality_level", "materiality_evidence"}
    if not required.issubset(relationships.columns):
        return out

    as_of_date = as_of if isinstance(as_of, date) else _iso(as_of)
    if as_of_date is None:
        return out

    rel = relationships.copy().fillna("")
    rel["change_type"] = rel["change_type"].astype(str).str.casefold().str.strip()
    rel["materiality_level"] = rel["materiality_level"].astype(str).str.casefold().str.strip()
    rel = rel[
        rel["change_type"].isin(CHANGE_TYPES)
        & rel["materiality_level"].isin(MATERIALITY_LEVELS)
        & rel["change_date"].astype(str).str.strip().ne("")
        & rel["materiality_evidence"].astype(str).str.strip().ne("")
        & rel["source_url"].astype(str).str.startswith(("https://", "http://"))
        & rel["active"].map(_bool)
        & rel["direction"].isin({"positive", "two_sided"})
        & rel["relationship_type"].isin({"customer_supplier", "supplier_customer", "operational_dependency"})
    ].copy()
    if rel.empty:
        return out

    rel["__change_date"] = pd.to_datetime(rel["change_date"], errors="coerce")
    rel["__age"] = (pd.Timestamp(as_of_date) - rel["__change_date"]).dt.days
    rel = rel[rel["__age"].between(0, recent_days, inclusive="both")]
    if rel.empty:
        return out
    rel["__mat"] = rel["materiality_level"].map(MATERIALITY_PRIORITY).fillna(0)

    ticker_to_idx = {_text(r.get("Ticker")): i for i, r in out.iterrows() if _text(r.get("Ticker"))}

    def source_strength(row: pd.Series) -> int:
        report = _bool(row.get("Report Delta kandidat"))
        pos = _num(row.get("Report Delta positiva")); neg = _num(row.get("Report Delta negativa"))
        mgmt = _bool(row.get("Ledningssignal kandidat")) and not _bool(row.get("Ledningssignal varning"))
        if report and math.isfinite(pos) and pos >= 4 and (not math.isfinite(neg) or neg <= 0) and mgmt:
            return 3
        if report and math.isfinite(pos) and pos >= 4 and (not math.isfinite(neg) or neg <= 0):
            return 2
        if mgmt:
            return 1
        return 0

    active_sources = {t: source_strength(out.loc[i]) for t, i in ticker_to_idx.items()}
    active_sources = {t: s for t, s in active_sources.items() if s > 0}
    if not active_sources:
        return out

    for ticker, idx in ticker_to_idx.items():
        matches = rel[(rel["target_ticker"].astype(str).str.strip() == ticker) & rel["source_ticker"].isin(active_sources.keys())].copy()
        if matches.empty:
            continue
        matches["__source_strength"] = matches["source_ticker"].map(active_sources).fillna(0)
        matches = matches.sort_values(["__mat", "__source_strength", "__age", "source_ticker"], ascending=[False, False, True, True])
        best = matches.iloc[0]
        row = out.loc[idx]
        own_fund = _num(row.get("Fundamental upptäckt antal"))
        own_neg = _bool(row.get("Ledningssignal varning")) or _num(row.get("Report Delta negativa")) >= 2 or "marknaden säger emot" in _text(row.get("Report Delta status")).casefold()
        m1 = _num(row.get("1 mån")); ran = math.isfinite(m1) and m1 > 0.12
        age = int(best["__age"])
        mat = _text(best["materiality_level"]).casefold()
        materiality_supported = MATERIALITY_PRIORITY.get(mat, 0) >= 2
        candidate = bool(materiality_supported and own_fund >= 1 and not own_neg and not ran)
        strong = bool(candidate and age <= fresh_days and MATERIALITY_PRIORITY.get(mat, 0) >= 3 and int(best["__source_strength"]) >= 2)

        if own_neg:
            status = "Relationsförändring – eget motbevis väger tyngre"; candidate = strong = False
        elif ran:
            status = "Relationsförändring – aktien har redan rört sig tydligt"; candidate = strong = False
        elif own_fund < 1:
            status = "Relationsförändring – saknar eget fundamentalt stöd"; candidate = strong = False
        elif not materiality_supported:
            status = "Relationsförändring verifierad – betydelsen är inte tillräckligt belagd"; candidate = strong = False
        elif strong:
            status = "Färsk och tydligt belagd relationsförändring"
        elif candidate:
            status = "Verifierad relationsförändring"
        else:
            status = "Verifierad relationsförändring – bevaka"

        source_ticker = _text(best["source_ticker"])
        sidx = ticker_to_idx.get(source_ticker)
        source_name = _text(out.at[sidx, "Namn"]) if sidx is not None and "Namn" in out.columns else source_ticker
        out.at[idx, "Relationsförändring status"] = status
        out.at[idx, "Relationsförändring kandidat"] = candidate
        out.at[idx, "Relationsförändring stark"] = strong
        out.at[idx, "Relationsförändring typ"] = _text(best["change_type"])
        out.at[idx, "Relationsförändring datum"] = _text(best["change_date"])
        out.at[idx, "Relationsförändring ålder dagar"] = age
        out.at[idx, "Relationsförändring materialitet"] = mat
        out.at[idx, "Relationsförändring materialitet evidens"] = _text(best["materiality_evidence"])
        out.at[idx, "Relationsförändring källbolag"] = source_name
        out.at[idx, "Relationsförändring evidens"] = _text(best.get("evidence_label"))
        out.at[idx, "Relationsförändring källa"] = _text(best["source_url"])
        out.at[idx, "Relationsförändring förklaring"] = (
            f"Relationen till {source_name} har en explicit verifierad förändring ({_text(best['change_type'])}) daterad {_text(best['change_date'])}. "
            f"Omfattningen klassas som {mat} utifrån källan: {_text(best['materiality_evidence'])}. "
            "Borsify antar inte någon intäktseffekt som inte uttryckligen är källbelagd."
        )
    return out


def select_relationship_change_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    if df is None or df.empty or quota <= 0 or "Relationsförändring kandidat" not in df.columns:
        return []
    w = df[df["Relationsförändring kandidat"].fillna(False).astype(bool)].copy()
    if w.empty:
        return []
    w["__strong"] = w.get("Relationsförändring stark", False).fillna(False).astype(int)
    w["__mat"] = w.get("Relationsförändring materialitet", "unknown").astype(str).str.casefold().map(MATERIALITY_PRIORITY).fillna(0)
    w["__age"] = pd.to_numeric(w.get("Relationsförändring ålder dagar"), errors="coerce").fillna(99999)
    w["__fund"] = pd.to_numeric(w.get("Fundamental upptäckt antal"), errors="coerce").fillna(0)
    w["__ticker"] = w.get("Ticker", pd.Series("", index=w.index)).astype(str)
    w = w.sort_values(["__strong", "__mat", "__age", "__fund", "__ticker"], ascending=[False, False, True, False, True])
    return [(idx, "Relationsförändring") for idx in w.index[:quota]]
