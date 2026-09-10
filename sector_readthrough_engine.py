from __future__ import annotations

"""Sector Read-through Engine.

Use strong *observed* changes in one company as a conservative clue for peers in the
same Yahoo sector/industry. This is not a causal or supply-chain model: a peer only
becomes a discovery candidate when it already has its own fundamental discovery
support, has no observed fresh negative warning, and has not obviously run away.

No score is created. The output is categorical audit evidence only.
"""

from typing import Any
import math
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else float("nan")
    except Exception:
        return float("nan")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return False
    return bool(value)


def _source_strength(row: pd.Series) -> tuple[int, str]:
    """Return conservative source strength and a plain-language source label."""
    report = _bool(row.get("Report Delta kandidat"))
    report_pos = _num(row.get("Report Delta positiva"))
    report_neg = _num(row.get("Report Delta negativa"))
    management = _bool(row.get("Ledningssignal kandidat"))
    management_warning = _bool(row.get("Ledningssignal varning"))

    if report and report_pos >= 4 and (not math.isfinite(report_neg) or report_neg <= 0) and management and not management_warning:
        return 3, "stark rapportförbättring + konkret positiv ledningssignal"
    if report and report_pos >= 4 and (not math.isfinite(report_neg) or report_neg <= 0):
        return 2, "bred positiv rapportförändring"
    if management and not management_warning:
        return 1, "flera konkreta positiva ledningssignaler"
    return 0, ""


def add_sector_readthrough(df: pd.DataFrame) -> pd.DataFrame:
    """Annotate peer read-through without inventing company-specific evidence.

    A target requires:
    - same non-empty sector as at least one strong source company,
    - its own transparent Fundamental Discovery support,
    - no own fresh report/management warning,
    - no >12% one-month run-up (avoid calling an already-run peer an underreaction).

    Same industry and multiple independent source companies strengthen the label, but
    are not converted to a score.
    """
    if df is None:
        return pd.DataFrame()
    out = df.copy()
    defaults = {
        "Sektorläsning status": "Ingen verifierbar sektorläsning",
        "Sektorläsning kandidat": False,
        "Sektorläsning stark": False,
        "Sektorläsning källor antal": 0,
        "Sektorläsning källbolag": "",
        "Sektorläsning källa": "",
        "Sektorläsning nivå": "",
        "Sektorläsning förklaring": "",
    }
    for col, value in defaults.items():
        out[col] = value
    if out.empty or "Sektor" not in out.columns:
        return out

    sources: list[tuple[Any, str, str, int, str]] = []
    for idx, row in out.iterrows():
        strength, why = _source_strength(row)
        sector = _text(row.get("Sektor"))
        if strength > 0 and sector:
            sources.append((idx, sector, _text(row.get("Bransch")), strength, why))

    for idx, row in out.iterrows():
        sector = _text(row.get("Sektor"))
        if not sector:
            continue
        peer_sources = [s for s in sources if s[0] != idx and s[1].casefold() == sector.casefold()]
        if not peer_sources:
            continue

        own_report_warning = "marknaden säger emot" in _text(row.get("Report Delta status")).casefold() or _num(row.get("Report Delta negativa")) >= 2
        own_mgmt_warning = _bool(row.get("Ledningssignal varning"))
        own_fundamental = _num(row.get("Fundamental upptäckt antal"))
        one_month = _num(row.get("1 mån"))
        already_ran = math.isfinite(one_month) and one_month > 0.12

        industry = _text(row.get("Bransch"))
        same_industry = [s for s in peer_sources if industry and s[2] and s[2].casefold() == industry.casefold()]
        ordered = sorted(peer_sources, key=lambda s: (-s[3], _text(out.at[s[0], "Ticker"])))
        names = [_text(out.at[s[0], "Namn"]) or _text(out.at[s[0], "Ticker"]) for s in ordered]
        source_descriptions = [f"{names[i]}: {s[4]}" for i, s in enumerate(ordered[:3])]

        candidate = bool(own_fundamental >= 1 and not own_report_warning and not own_mgmt_warning and not already_ran)
        strong = bool(candidate and (len({s[0] for s in peer_sources}) >= 2 or (same_industry and max(s[3] for s in same_industry) >= 2)))
        level = "samma bransch" if same_industry else "samma sektor"

        if own_report_warning or own_mgmt_warning:
            status = "Sektor positiv – eget motbevis väger tyngre"
            candidate = False
            strong = False
        elif already_ran:
            status = "Sektor positiv – peer har redan rört sig tydligt"
            candidate = False
            strong = False
        elif own_fundamental < 1:
            status = "Sektor positiv – saknar eget fundamentalt stöd"
            candidate = False
            strong = False
        elif strong:
            status = "Stark sektorläsning för peer"
        elif candidate:
            status = "Möjlig sektorläsning för peer"
        else:
            status = "Sektorindikering observerad"

        out.at[idx, "Sektorläsning status"] = status
        out.at[idx, "Sektorläsning kandidat"] = bool(candidate)
        out.at[idx, "Sektorläsning stark"] = bool(strong)
        out.at[idx, "Sektorläsning källor antal"] = len({s[0] for s in peer_sources})
        out.at[idx, "Sektorläsning källbolag"] = ", ".join(dict.fromkeys(names[:3]))
        out.at[idx, "Sektorläsning källa"] = " | ".join(source_descriptions)
        out.at[idx, "Sektorläsning nivå"] = level
        out.at[idx, "Sektorläsning förklaring"] = (
            f"{level.capitalize()} visar färsk positiv förändring via {', '.join(dict.fromkeys(names[:3]))}. "
            + ("Peer har eget fundamentalt discovery-stöd. " if own_fundamental >= 1 else "Peer saknar eget fundamentalt discovery-stöd. ")
            + ("Kursen har redan stigit >12 % på en månad. " if already_ran else "")
            + "Detta är en sektorsignal, inte bevis för att samma förändring gäller peer-bolaget."
        )
    return out


def select_sector_readthrough_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    if df is None or df.empty or quota <= 0 or "Sektorläsning kandidat" not in df.columns:
        return []
    work = df[df["Sektorläsning kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__strong"] = work.get("Sektorläsning stark", False).fillna(False).astype(int)
    work["__sources"] = pd.to_numeric(work.get("Sektorläsning källor antal"), errors="coerce").fillna(0)
    work["__fund"] = pd.to_numeric(work.get("Fundamental upptäckt antal"), errors="coerce").fillna(0)
    work["__m1"] = pd.to_numeric(work.get("1 mån"), errors="coerce").fillna(999)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(["__strong", "__sources", "__fund", "__m1", "__ticker"], ascending=[False, False, False, True, True])
    return [(idx, "Sektorläsning") for idx in work.index[:quota]]
