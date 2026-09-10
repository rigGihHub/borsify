from __future__ import annotations

"""Verified Company Relationship Engine.

A conservative evidence layer for named customer/supplier, ownership, commodity and
market-exposure relationships. Unlike the heuristic value-chain engine, this module
only acts on explicit records carrying source metadata. Missing evidence stays
missing; an inferred industry relationship is never upgraded to "verified".

The engine is intentionally score-free. It can contribute at most one cross-company
discovery doorway via finalist_selection, sharing the existing read-through quota.
"""

from pathlib import Path
from typing import Any
import math
import pandas as pd

REQUIRED_COLUMNS = {
    "source_ticker", "target_ticker", "relationship_type", "direction",
    "evidence_label", "source_url", "source_date", "verified_at", "active",
}
ALLOWED_TYPES = {
    "supplier_customer", "customer_supplier", "ownership",
    "commodity_exposure", "market_exposure", "operational_dependency",
}
ALLOWED_DIRECTIONS = {"positive", "negative", "two_sided"}

# Only directional operating links are allowed to create cross-company discovery.
# Ownership remains useful context but is not evidence that a portfolio company should
# follow the investment company's operating momentum.
OPERATING_READTHROUGH_TYPES = {"customer_supplier", "supplier_customer", "operational_dependency"}
RELATIONSHIP_TYPE_PRIORITY = {
    "customer_supplier": 4,
    "operational_dependency": 3,
    "supplier_customer": 2,
    "commodity_exposure": 2,
    "market_exposure": 1,
    "ownership": 0,
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


def load_verified_relationships(path: str | Path | None = None) -> pd.DataFrame:
    """Load registry records; malformed or unverifiable rows are discarded."""
    path = Path(path) if path is not None else Path(__file__).with_name("verified_company_relationships.csv")
    if not path.exists():
        return pd.DataFrame(columns=sorted(REQUIRED_COLUMNS))
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=sorted(REQUIRED_COLUMNS))
    if not REQUIRED_COLUMNS.issubset(df.columns):
        return pd.DataFrame(columns=sorted(REQUIRED_COLUMNS))
    out = df.copy()
    out = out[out["source_ticker"].astype(str).str.strip().ne("")]
    out = out[out["target_ticker"].astype(str).str.strip().ne("")]
    out = out[out["source_ticker"].astype(str).str.strip() != out["target_ticker"].astype(str).str.strip()]
    out = out[out["relationship_type"].isin(ALLOWED_TYPES)]
    out = out[out["direction"].isin(ALLOWED_DIRECTIONS)]
    out = out[out["evidence_label"].astype(str).str.strip().ne("")]
    out = out[out["source_url"].astype(str).str.startswith(("https://", "http://"))]
    out = out[out["source_date"].astype(str).str.strip().ne("")]
    out = out[out["verified_at"].astype(str).str.strip().ne("")]
    out = out[out["active"].map(_bool)]
    return out.reset_index(drop=True)


def add_verified_relationships(df: pd.DataFrame, relationships: pd.DataFrame | None = None) -> pd.DataFrame:
    """Attach only explicit verified relationships to current discovery rows.

    A source company still needs a fresh positive direct-company change. A target
    needs its own fundamental support, no fresh negative contradiction, and no >12%
    one-month run-up. This mirrors the conservative cross-company safeguards already
    used by the value-chain layer while replacing heuristic adjacency with evidence.
    """
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    defaults = {
        "Verifierad relation status": "Ingen verifierad bolagsrelation",
        "Verifierad relation kandidat": False,
        "Verifierad relation stark": False,
        "Verifierad relation källor antal": 0,
        "Verifierad relation källbolag": "",
        "Verifierad relation typ": "",
        "Verifierad relation evidens": "",
        "Verifierad relation källa": "",
        "Verifierad relation förklaring": "",
        "Verifierad relation operativ": False,
        "Verifierad relation prioritet": 0,
    }
    for c, v in defaults.items():
        out[c] = v
    if out.empty:
        return out

    rel = load_verified_relationships() if relationships is None else relationships.copy()
    if rel is None or rel.empty or not REQUIRED_COLUMNS.issubset(rel.columns):
        return out
    # Apply the same strict evidence validation to injected/test registries.
    rel = rel.copy().fillna("")
    rel = rel[rel["relationship_type"].isin(ALLOWED_TYPES)]
    rel = rel[rel["direction"].isin(ALLOWED_DIRECTIONS)]
    rel = rel[rel["source_url"].astype(str).str.startswith(("https://", "http://"))]
    rel = rel[rel["evidence_label"].astype(str).str.strip().ne("")]
    rel = rel[rel["source_date"].astype(str).str.strip().ne("")]
    rel = rel[rel["verified_at"].astype(str).str.strip().ne("")]
    rel = rel[rel["active"].map(_bool)]
    if rel.empty:
        return out

    ticker_to_idx = {_text(row.get("Ticker")): idx for idx, row in out.iterrows() if _text(row.get("Ticker"))}

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

    active_sources: dict[str, int] = {}
    for ticker, idx in ticker_to_idx.items():
        strength = source_strength(out.loc[idx])
        if strength > 0:
            active_sources[ticker] = strength

    for ticker, idx in ticker_to_idx.items():
        matches = rel[(rel["target_ticker"].astype(str).str.strip() == ticker) & rel["source_ticker"].isin(active_sources.keys())].copy()
        if matches.empty:
            continue
        row = out.loc[idx]
        own_fund = _num(row.get("Fundamental upptäckt antal"))
        own_neg = _bool(row.get("Ledningssignal varning")) or _num(row.get("Report Delta negativa")) >= 2 or "marknaden säger emot" in _text(row.get("Report Delta status")).casefold()
        m1 = _num(row.get("1 mån")); ran = math.isfinite(m1) and m1 > 0.12
        matches["__strength"] = matches["source_ticker"].map(active_sources).fillna(0)
        matches["__rel_priority"] = matches["relationship_type"].map(RELATIONSHIP_TYPE_PRIORITY).fillna(0)
        matches["__operating"] = matches["relationship_type"].isin(OPERATING_READTHROUGH_TYPES) & matches["direction"].isin({"positive", "two_sided"})
        matches = matches.sort_values(["__operating", "__rel_priority", "__strength", "source_ticker"], ascending=[False, False, False, True])
        operating_matches = matches[matches["__operating"]].copy()
        has_operating_link = not operating_matches.empty
        candidate = bool(has_operating_link and own_fund >= 1 and not own_neg and not ran)
        independent_sources = operating_matches["source_ticker"].nunique() if has_operating_link else 0
        strong = bool(candidate and (independent_sources >= 2 or operating_matches["__strength"].max() >= 3))
        if not has_operating_link:
            status = "Verifierad relation – kontext, inte operativ read-through"; candidate = strong = False
        elif own_neg:
            status = "Verifierad relation – eget motbevis väger tyngre"; candidate = strong = False
        elif ran:
            status = "Verifierad relation – aktien har redan rört sig tydligt"; candidate = strong = False
        elif own_fund < 1:
            status = "Verifierad relation – saknar eget fundamentalt stöd"; candidate = strong = False
        elif strong:
            status = "Stark verifierad bolagsrelation"
        else:
            status = "Verifierad bolagsrelation"

        names, types, evid, urls = [], [], [], []
        display_matches = operating_matches if has_operating_link else matches
        for _, r in display_matches.head(3).iterrows():
            st = _text(r["source_ticker"]); sidx = ticker_to_idx.get(st)
            names.append(_text(out.at[sidx, "Namn"]) if sidx is not None and "Namn" in out.columns else st)
            types.append(_text(r["relationship_type"]))
            evid.append(_text(r["evidence_label"]))
            urls.append(_text(r["source_url"]))
        out.at[idx, "Verifierad relation status"] = status
        out.at[idx, "Verifierad relation kandidat"] = candidate
        out.at[idx, "Verifierad relation stark"] = strong
        out.at[idx, "Verifierad relation källor antal"] = independent_sources
        out.at[idx, "Verifierad relation källbolag"] = ", ".join(dict.fromkeys(names))
        out.at[idx, "Verifierad relation typ"] = "; ".join(dict.fromkeys(types))
        out.at[idx, "Verifierad relation evidens"] = "; ".join(dict.fromkeys(evid))
        out.at[idx, "Verifierad relation källa"] = "; ".join(dict.fromkeys(urls))
        out.at[idx, "Verifierad relation operativ"] = has_operating_link
        out.at[idx, "Verifierad relation prioritet"] = int(display_matches["__rel_priority"].max()) if not display_matches.empty else 0
        out.at[idx, "Verifierad relation förklaring"] = (
            f"Det finns explicit källbelagd ekonomisk relation till {', '.join(dict.fromkeys(names))}. "
            + ("Relationen är riktad från kund/operativ källa mot target och kan därför användas som försiktig read-through. " if has_operating_link else "Relationen är verifierad kontext men används inte som operativ read-through. ")
            + ("Target-bolaget har eget fundamentalt discovery-stöd. " if own_fund >= 1 else "Target-bolaget saknar eget fundamentalt discovery-stöd. ")
            + "Relationen används som discovery-ledtråd, inte som bevis för att target-bolagets resultat måste följa källbolagets."
        )
    return out


def select_verified_relationship_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    if df is None or df.empty or quota <= 0 or "Verifierad relation kandidat" not in df.columns:
        return []
    w = df[df["Verifierad relation kandidat"].fillna(False).astype(bool)].copy()
    if w.empty:
        return []
    w["__strong"] = w.get("Verifierad relation stark", False).fillna(False).astype(int)
    w["__sources"] = pd.to_numeric(w.get("Verifierad relation källor antal"), errors="coerce").fillna(0)
    w["__priority"] = pd.to_numeric(w.get("Verifierad relation prioritet"), errors="coerce").fillna(0)
    w["__fund"] = pd.to_numeric(w.get("Fundamental upptäckt antal"), errors="coerce").fillna(0)
    w["__m1"] = pd.to_numeric(w.get("1 mån"), errors="coerce").fillna(999)
    w["__ticker"] = w.get("Ticker", pd.Series("", index=w.index)).astype(str)
    w = w.sort_values(["__strong", "__priority", "__sources", "__fund", "__m1", "__ticker"], ascending=[False, False, False, False, True, True])
    return [(idx, "Verifierad relation") for idx in w.index[:quota]]
