from __future__ import annotations

"""Relationship Data Builder for Borsify.

Turns manually researched, source-backed relationship records into a deterministic,
auditable registry. This module deliberately does *not* scrape or infer relationships.
Only records with explicit source metadata pass. Its purpose is to make it easy to
expand verified_company_relationships.csv without weakening the evidence standard.
"""

from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse
import math
import pandas as pd

from verified_relationship_engine import (
    ALLOWED_DIRECTIONS,
    ALLOWED_TYPES,
    REQUIRED_COLUMNS,
)

PRIMARY_SOURCE_KINDS = {
    "company_portfolio_page",
    "company_ir",
    "annual_report",
    "interim_report",
    "exchange_filing",
    "regulatory_filing",
}

OPTIONAL_COLUMNS = {
    "source_kind",
    "source_title",
    "relationship_note",
    "change_type",
    "change_date",
    "materiality_level",
    "materiality_evidence",
}


def _text(v: Any) -> str:
    return str(v or "").strip()


def _bool(v: Any) -> bool:
    try:
        if pd.isna(v):
            return False
    except Exception:
        pass
    if isinstance(v, str):
        return v.strip().casefold() in {"1", "true", "yes", "ja", "active"}
    return bool(v)


def _iso_date(v: Any) -> date | None:
    s = _text(v)
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return None


def _normalized_record(record: dict[str, Any]) -> dict[str, Any]:
    out = {k: _text(record.get(k)) for k in (REQUIRED_COLUMNS | OPTIONAL_COLUMNS)}
    out["source_ticker"] = out["source_ticker"].upper()
    out["target_ticker"] = out["target_ticker"].upper()
    out["relationship_type"] = out["relationship_type"].casefold()
    out["direction"] = out["direction"].casefold()
    out["source_kind"] = out["source_kind"].casefold()
    out["change_type"] = out["change_type"].casefold()
    out["materiality_level"] = out["materiality_level"].casefold()
    out["active"] = "true" if _bool(record.get("active")) else "false"
    return out


def validate_relationship_record(
    record: dict[str, Any],
    *,
    as_of: str | date | None = None,
    require_primary_source: bool = True,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate one source-backed registry row without making any inference."""
    r = _normalized_record(record)
    errors: list[str] = []

    missing = [c for c in REQUIRED_COLUMNS if not _text(r.get(c))]
    if missing:
        errors.append("missing:" + ",".join(sorted(missing)))
    if r["source_ticker"] == r["target_ticker"] and r["source_ticker"]:
        errors.append("self_relationship")
    if r["relationship_type"] not in ALLOWED_TYPES:
        errors.append("invalid_relationship_type")
    if r["direction"] not in ALLOWED_DIRECTIONS:
        errors.append("invalid_direction")
    if not _bool(r["active"]):
        errors.append("inactive")

    parsed = urlparse(r["source_url"])
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("source_must_be_https")

    source_date = _iso_date(r["source_date"])
    verified_at = _iso_date(r["verified_at"])
    if source_date is None:
        errors.append("invalid_source_date")
    if verified_at is None:
        errors.append("invalid_verified_at")
    if source_date and verified_at and source_date > verified_at:
        errors.append("source_after_verification")

    if as_of is None:
        as_of_date = date.today()
    elif isinstance(as_of, date):
        as_of_date = as_of
    else:
        as_of_date = _iso_date(as_of)
    if as_of_date and verified_at and verified_at > as_of_date:
        errors.append("verification_in_future")

    if require_primary_source:
        if r["source_kind"] not in PRIMARY_SOURCE_KINDS:
            errors.append("non_primary_or_missing_source_kind")

    if len(r["evidence_label"]) < 8:
        errors.append("evidence_label_too_short")
    return (not errors), errors, r


def build_relationship_registry(
    candidates: pd.DataFrame | Iterable[dict[str, Any]],
    *,
    existing: pd.DataFrame | None = None,
    as_of: str | date | None = None,
    require_primary_source: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate, normalize and de-duplicate candidate records.

    Returns (registry, rejected). Newer verification wins for the same directed
    source->target relationship type. Rejections always retain a reason.
    """
    if isinstance(candidates, pd.DataFrame):
        rows = candidates.to_dict("records")
    else:
        rows = list(candidates or [])

    valid: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for raw in rows:
        ok, errors, norm = validate_relationship_record(
            raw, as_of=as_of, require_primary_source=require_primary_source
        )
        if ok:
            valid.append(norm)
        else:
            bad = dict(norm)
            bad["rejection_reason"] = ";".join(errors)
            rejected.append(bad)

    frames: list[pd.DataFrame] = []
    if existing is not None and not existing.empty:
        ex = existing.copy()
        for c in OPTIONAL_COLUMNS:
            if c not in ex.columns:
                ex[c] = ""
        frames.append(ex)
    if valid:
        frames.append(pd.DataFrame(valid))

    columns = sorted(REQUIRED_COLUMNS | OPTIONAL_COLUMNS)
    if not frames:
        registry = pd.DataFrame(columns=columns)
    else:
        registry = pd.concat(frames, ignore_index=True, sort=False)
        for c in columns:
            if c not in registry.columns:
                registry[c] = ""
        registry["__verified"] = pd.to_datetime(registry["verified_at"], errors="coerce")
        registry["__row"] = range(len(registry))
        registry = registry.sort_values(["__verified", "__row"], ascending=[True, True])
        registry = registry.drop_duplicates(
            subset=["source_ticker", "target_ticker", "relationship_type"], keep="last"
        )
        registry = registry.sort_values(
            ["source_ticker", "target_ticker", "relationship_type"], kind="stable"
        )
        registry = registry.drop(columns=["__verified", "__row"]).reset_index(drop=True)
        registry = registry[[c for c in columns if c in registry.columns]]

    rejected_df = pd.DataFrame(rejected)
    return registry, rejected_df


def relationship_registry_health(
    registry: pd.DataFrame,
    *,
    as_of: str | date | None = None,
    stale_after_days: int = 550,
) -> dict[str, Any]:
    """Small, transparent audit summary for the advanced UI."""
    if registry is None or registry.empty:
        return {
            "relations": 0,
            "source_companies": 0,
            "target_companies": 0,
            "primary_source_share": float("nan"),
            "stale_relations": 0,
            "operating_relations": 0,
            "customer_supplier_relations": 0,
        }
    d = registry.copy()
    as_of_date = date.today() if as_of is None else (as_of if isinstance(as_of, date) else _iso_date(as_of))
    verified = pd.to_datetime(d.get("verified_at"), errors="coerce")
    stale = 0
    if as_of_date is not None:
        age = (pd.Timestamp(as_of_date) - verified).dt.days
        stale = int((age > stale_after_days).fillna(True).sum())
    kinds = d.get("source_kind", pd.Series("", index=d.index)).astype(str).str.casefold()
    primary_share = float(kinds.isin(PRIMARY_SOURCE_KINDS).mean()) if len(d) else float("nan")
    rel_types = d.get("relationship_type", pd.Series("", index=d.index)).astype(str).str.casefold()
    return {
        "relations": int(len(d)),
        "source_companies": int(d.get("source_ticker", pd.Series(dtype=str)).nunique()),
        "target_companies": int(d.get("target_ticker", pd.Series(dtype=str)).nunique()),
        "primary_source_share": primary_share,
        "stale_relations": stale,
        "operating_relations": int(rel_types.isin({"customer_supplier", "operational_dependency"}).sum()),
        "customer_supplier_relations": int(rel_types.eq("customer_supplier").sum()),
    }


def write_relationship_registry(registry: pd.DataFrame, path: str | Path) -> Path:
    """Write a deterministic registry file. Caller decides when a write is appropriate."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    registry.to_csv(p, index=False, lineterminator="\n")
    return p
