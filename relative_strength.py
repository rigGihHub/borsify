from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _market_bucket(symbol: str) -> str:
    s = str(symbol or "").upper()
    suffixes = {
        ".ST": "Sverige", ".CO": "Danmark", ".OL": "Norge", ".HE": "Finland",
        ".DE": "Tyskland", ".L": "Storbritannien", ".TO": "Kanada", ".V": "Kanada",
        ".PA": "Frankrike", ".AS": "Nederländerna", ".BR": "Belgien", ".MI": "Italien",
        ".MC": "Spanien", ".SW": "Schweiz", ".LS": "Portugal",
    }
    for suffix, name in suffixes.items():
        if s.endswith(suffix):
            return name
    return "USA"


def _score_excess(excess: float) -> float:
    if not np.isfinite(excess):
        return 50.0
    return float(np.clip((excess + .15) / .30 * 100.0, 0.0, 100.0))


def _clean_label(v: Any) -> str:
    s = str(v or "").strip()
    return s if s and s.lower() not in {"nan", "none"} else "Okänd"


def _peer_group_indices(out: pd.DataFrame, idx: Any, market: str, sector: str, industry: str) -> list[Any]:
    """Return conservative peer candidates from the current scan.

    Priority: same market + sector + industry. If that is too small, fall back to
    same market + sector. A valid peer group needs at least 3 *other* stocks.
    """
    mask = out.index != idx
    same_market = out["Jämförelsemarknad"].eq(market)
    same_sector = out["_sector_tmp"].eq(sector)
    same_industry = out["_industry_tmp"].eq(industry)

    if industry.lower() != "okänd":
        exact = out.index[mask & same_market & same_sector & same_industry].tolist()
        if len(exact) >= 3:
            return exact

    if sector.lower() != "okänd":
        fallback = out.index[mask & same_market & same_sector].tolist()
        if len(fallback) >= 3:
            return fallback
    return []


def _peer_median(out: pd.DataFrame, peer_indices: list[Any], col: str) -> tuple[float, int]:
    if not peer_indices:
        return np.nan, 0
    values = pd.to_numeric(out.loc[peer_indices, col], errors="coerce").dropna()
    if len(values) < 3:
        return np.nan, int(len(values))
    return float(values.median()), int(len(values))


def add_relative_strength(df: pd.DataFrame) -> pd.DataFrame:
    """Benchmark 2.0: compare stock with home market, sector and nearby peers.

    This remains a scan-relative comparison. Borsify does not fabricate an official
    country index or sector index when external benchmark data is unavailable.
    Peers are only used with at least 3 other comparable stocks in the same market.
    Relative strength is confirmation/tiebreaking evidence; it does not rescue a
    weak fundamental case by itself.
    """
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()

    out = df.copy()
    old = [
        "Jämförelsemarknad", "Marknad 1 mån", "Marknad 3 mån",
        "Sektor 1 mån", "Sektor 3 mån", "Peer 1 mån", "Peer 3 mån",
        "Relativ marknad 1 mån", "Relativ marknad 3 mån",
        "Relativ sektor 1 mån", "Relativ sektor 3 mån",
        "Relativ peer 1 mån", "Relativ peer 3 mån",
        "Sektorstyrka 1 mån", "Sektorstyrka 3 mån",
        "Relativ styrka", "Relativ styrka förklaring", "Relativ styrka underlag",
    ]
    out = out.drop(columns=[c for c in old if c in out.columns], errors="ignore")
    out["Jämförelsemarknad"] = out.get("Ticker", pd.Series("", index=out.index)).map(_market_bucket)

    for col in ["1 mån", "3 mån"]:
        out[col] = pd.to_numeric(out.get(col, pd.Series(np.nan, index=out.index)), errors="coerce")

    market_stats: dict[tuple[str, str], float] = {}
    for market, g in out.groupby("Jämförelsemarknad", dropna=False):
        for col in ["1 mån", "3 mån"]:
            market_stats[(str(market), col)] = float(g[col].median()) if g[col].notna().sum() >= 3 else np.nan

    out["_sector_tmp"] = out.get("Sektor", pd.Series("Okänd", index=out.index)).map(_clean_label)
    out["_industry_tmp"] = out.get("Bransch", pd.Series("Okänd", index=out.index)).map(_clean_label)

    sector_stats: dict[tuple[str, str, str], float] = {}
    sector_counts: dict[tuple[str, str, str], int] = {}
    for (market, sector), g in out.groupby(["Jämförelsemarknad", "_sector_tmp"], dropna=False):
        for col in ["1 mån", "3 mån"]:
            count = int(g[col].notna().sum())
            sector_counts[(str(market), str(sector), col)] = count
            sector_stats[(str(market), str(sector), col)] = (
                float(g[col].median()) if count >= 3 and str(sector).lower() != "okänd" else np.nan
            )

    rows = []
    for idx, r in out.iterrows():
        market = str(r.get("Jämförelsemarknad") or "")
        sector = _clean_label(r.get("_sector_tmp"))
        industry = _clean_label(r.get("_industry_tmp"))
        m1 = _num(r.get("1 mån")); m3 = _num(r.get("3 mån"))
        market1 = _num(market_stats.get((market, "1 mån")))
        market3 = _num(market_stats.get((market, "3 mån")))
        sector1 = _num(sector_stats.get((market, sector, "1 mån")))
        sector3 = _num(sector_stats.get((market, sector, "3 mån")))

        peer_indices = _peer_group_indices(out, idx, market, sector, industry)
        peer1, peer_count1 = _peer_median(out, peer_indices, "1 mån")
        peer3, peer_count3 = _peer_median(out, peer_indices, "3 mån")

        rel_m1 = m1 - market1 if np.isfinite(m1) and np.isfinite(market1) else np.nan
        rel_m3 = m3 - market3 if np.isfinite(m3) and np.isfinite(market3) else np.nan
        rel_s1 = m1 - sector1 if np.isfinite(m1) and np.isfinite(sector1) else np.nan
        rel_s3 = m3 - sector3 if np.isfinite(m3) and np.isfinite(sector3) else np.nan
        rel_p1 = m1 - peer1 if np.isfinite(m1) and np.isfinite(peer1) else np.nan
        rel_p3 = m3 - peer3 if np.isfinite(m3) and np.isfinite(peer3) else np.nan
        sec_strength1 = sector1 - market1 if np.isfinite(sector1) and np.isfinite(market1) else np.nan
        sec_strength3 = sector3 - market3 if np.isfinite(sector3) and np.isfinite(market3) else np.nan

        components = []
        # Peer comparison gets meaningful weight when evidence exists, but broad
        # market and sector still anchor the comparison.
        for value, weight in [
            (rel_m1, .15), (rel_m3, .25),
            (rel_s1, .10), (rel_s3, .20),
            (rel_p1, .08), (rel_p3, .17),
            (sec_strength3, .05),
        ]:
            if np.isfinite(value):
                components.append((_score_excess(value), weight))
        if components:
            total_weight = sum(w for _, w in components)
            score = sum(s * w for s, w in components) / total_weight
        else:
            score = 50.0

        messages: list[tuple[float, str]] = []
        if np.isfinite(rel_m3):
            messages.append((abs(rel_m3), f"aktien har gått {abs(rel_m3):.1%} {'bättre' if rel_m3 > 0 else 'sämre'} än hemmamarknaden på tre månader"))
        if np.isfinite(rel_s3):
            messages.append((abs(rel_s3), f"aktien har gått {abs(rel_s3):.1%} {'bättre' if rel_s3 > 0 else 'sämre'} än sektorn på tre månader"))
        if np.isfinite(rel_p3):
            messages.append((abs(rel_p3), f"aktien har gått {abs(rel_p3):.1%} {'bättre' if rel_p3 > 0 else 'sämre'} än jämförbara bolag på tre månader"))
        if np.isfinite(sec_strength3):
            messages.append((abs(sec_strength3), f"sektorn har gått {abs(sec_strength3):.1%} {'bättre' if sec_strength3 > 0 else 'sämre'} än hemmamarknaden"))
        messages.sort(key=lambda x: x[0], reverse=True)
        explanation = "; ".join(text for _, text in messages[:3]) or "för få jämförbara aktier för en säker relativ jämförelse"

        sector_count = sector_counts.get((market, sector, "3 mån"), 0)
        basis_parts = [f"hemmamarknad: {market}"]
        if sector_count:
            basis_parts.append(f"{sector_count} aktier i samma sektor")
        if peer_count3 >= 3:
            peer_label = f"{peer_count3} jämförbara bolag"
            if industry.lower() != "okänd":
                exact_peers = out.loc[peer_indices, "_industry_tmp"].eq(industry).all() if peer_indices else False
                if exact_peers:
                    peer_label += f" i {industry}"
            basis_parts.append("peers: " + peer_label)
        else:
            basis_parts.append("peers: för lite underlag")

        rows.append({
            "Marknad 1 mån": market1, "Marknad 3 mån": market3,
            "Sektor 1 mån": sector1, "Sektor 3 mån": sector3,
            "Peer 1 mån": peer1, "Peer 3 mån": peer3,
            "Relativ marknad 1 mån": rel_m1, "Relativ marknad 3 mån": rel_m3,
            "Relativ sektor 1 mån": rel_s1, "Relativ sektor 3 mån": rel_s3,
            "Relativ peer 1 mån": rel_p1, "Relativ peer 3 mån": rel_p3,
            "Sektorstyrka 1 mån": sec_strength1, "Sektorstyrka 3 mån": sec_strength3,
            "Relativ styrka": float(score),
            "Relativ styrka förklaring": explanation,
            "Relativ styrka underlag": " · ".join(basis_parts),
        })

    rel = pd.DataFrame(rows, index=out.index)
    out = out.drop(columns=["_sector_tmp", "_industry_tmp"])
    return out.join(rel)


def relative_strength_label(row: pd.Series | dict[str, Any]) -> str:
    score = _num(row.get("Relativ styrka"))
    if not np.isfinite(score):
        return "För lite underlag"
    if score >= 68:
        return "Starkare än jämförelsen"
    if score >= 55:
        return "Något starkare än jämförelsen"
    if score >= 45:
        return "Ungefär i nivå med jämförelsen"
    return "Svagare än jämförelsen"
