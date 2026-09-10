from __future__ import annotations

"""Capital Allocation + Insider Cluster Radar.

A conservative discovery layer for owner-friendly capital allocation and clustered
insider buying. It creates no investment score. Missing data stays missing and a
positive signal can only open a small doorway to deep analysis.
"""

from typing import Any, Iterable
import math
import re

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _find_row(frame: pd.DataFrame | None, names: Iterable[str]) -> pd.Series:
    if frame is None or not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=float)
    lookup = {str(i).strip().lower(): i for i in frame.index}
    for name in names:
        key = str(name).strip().lower()
        if key in lookup:
            s = pd.to_numeric(frame.loc[lookup[key]], errors="coerce").dropna()
            if not s.empty:
                try:
                    s.index = pd.to_datetime(s.index, errors="coerce")
                    s = s[~s.index.isna()].sort_index(ascending=False)
                except Exception:
                    pass
                return s.astype(float)
    return pd.Series(dtype=float)


def _latest(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return _num(s.iloc[0]) if not s.empty else np.nan


def _previous(series: pd.Series) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    return _num(s.iloc[1]) if len(s) >= 2 else np.nan


def _signed_cash_outflow(value: float) -> float:
    """Normalize a cash-flow line that can be signed differently by providers."""
    if not np.isfinite(value):
        return np.nan
    return abs(value)


def _debt_change(balance: pd.DataFrame | None) -> float:
    debt = _find_row(balance, ["Total Debt"])
    cash = _find_row(balance, [
        "Cash Cash Equivalents And Short Term Investments",
        "Cash And Cash Equivalents",
        "Cash",
    ])
    if not debt.empty and not cash.empty:
        common = debt.index.intersection(cash.index)
        if len(common) >= 2:
            net = pd.to_numeric(debt.loc[common], errors="coerce") - pd.to_numeric(cash.loc[common], errors="coerce")
            net = net.dropna().sort_index(ascending=False)
            latest, prior = _latest(net), _previous(net)
            if np.isfinite(latest) and np.isfinite(prior) and abs(prior) > 0:
                return latest / abs(prior) - (1 if prior >= 0 else -1)
    latest, prior = _latest(debt), _previous(debt)
    if np.isfinite(latest) and np.isfinite(prior) and prior != 0:
        return latest / prior - 1
    return np.nan


def build_capital_allocation_metrics(
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    snapshot: dict[str, Any] | pd.Series | None = None,
) -> dict[str, Any]:
    """Extract observable buybacks, issuance, dividends and debt change.

    Buybacks are judged net of observed share issuance. A gross repurchase does not
    count as owner-friendly if similar/new issuance offsets it.
    """
    snap = snapshot if snapshot is not None else {}
    repurchase = _find_row(cashflow, [
        "Repurchase Of Capital Stock", "Repurchase Of Stock", "Common Stock Repurchase",
    ])
    issuance = _find_row(cashflow, [
        "Issuance Of Capital Stock", "Common Stock Issuance", "Issuance Of Common Stock",
    ])
    dividends = _find_row(cashflow, [
        "Cash Dividends Paid", "Common Stock Dividend Paid", "Payment Of Dividends",
    ])

    repurchase_cash = _signed_cash_outflow(_latest(repurchase))
    issuance_cash = _signed_cash_outflow(_latest(issuance))
    dividends_cash = _signed_cash_outflow(_latest(dividends))
    net_buyback = np.nan
    if np.isfinite(repurchase_cash) or np.isfinite(issuance_cash):
        net_buyback = (repurchase_cash if np.isfinite(repurchase_cash) else 0.0) - (issuance_cash if np.isfinite(issuance_cash) else 0.0)

    market_cap = _num(snap.get("Börsvärde") if hasattr(snap, "get") else np.nan)
    if not np.isfinite(market_cap):
        market_cap = _num(snap.get("Market Cap") if hasattr(snap, "get") else np.nan)
    if not np.isfinite(market_cap):
        market_cap = _num(snap.get("market_cap") if hasattr(snap, "get") else np.nan)

    buyback_yield = net_buyback / market_cap if np.isfinite(net_buyback) and np.isfinite(market_cap) and market_cap > 0 else np.nan
    issuance_yield = issuance_cash / market_cap if np.isfinite(issuance_cash) and np.isfinite(market_cap) and market_cap > 0 else np.nan
    dividend_yield_cash = dividends_cash / market_cap if np.isfinite(dividends_cash) and np.isfinite(market_cap) and market_cap > 0 else np.nan

    return {
        "Kapitalallokering nettoåterköp": net_buyback,
        "Kapitalallokering återköpsyield": buyback_yield,
        "Kapitalallokering emissionsyield": issuance_yield,
        "Kapitalallokering kontantutdelningsyield": dividend_yield_cash,
        "Kapitalallokering skuldtrend": _debt_change(balance),
    }


def _first_existing(frame: pd.DataFrame, names: Iterable[str]) -> str | None:
    lookup = {str(c).strip().lower(): c for c in frame.columns}
    for name in names:
        if name.lower() in lookup:
            return lookup[name.lower()]
    return None


def analyze_insider_cluster(
    transactions: pd.DataFrame | None,
    as_of: Any | None = None,
    lookback_days: int = 120,
) -> dict[str, Any]:
    """Detect independent open-market insider purchases without inventing intent.

    Awards, option exercises and grants are ignored because they are not voluntary
    open-market purchases. A cluster needs purchases by at least two distinct people.
    """
    base = {
        "Insider köp antal": 0,
        "Insider köpare antal": 0,
        "Insider sälj antal": 0,
        "Insider köp värde": np.nan,
        "Insider kluster": False,
        "Insider starkt kluster": False,
        "Insider period dagar": int(lookback_days),
        "Insider förklaring": "Ingen verifierbar insidertransaktionsdata",
    }
    if transactions is None or not isinstance(transactions, pd.DataFrame) or transactions.empty:
        return base

    df = transactions.copy()
    date_col = _first_existing(df, ["Start Date", "Date", "Transaction Date", "Insider Trading Date"])
    if date_col:
        dates = pd.to_datetime(df[date_col], errors="coerce", utc=True)
    else:
        dates = pd.to_datetime(df.index, errors="coerce", utc=True)
    now = pd.Timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    cutoff = now - pd.Timedelta(days=int(lookback_days))
    keep = dates.notna() & (dates <= now) & (dates >= cutoff)
    df = df.loc[keep].copy()
    if df.empty:
        base["Insider förklaring"] = f"Inga verifierbara insidertransaktioner senaste {lookback_days} dagarna"
        return base

    tx_col = _first_existing(df, ["Transaction", "Transaction Text", "Text", "Type", "Transaction Type"])
    person_col = _first_existing(df, ["Insider", "Insider Name", "Name", "Holder"])
    value_col = _first_existing(df, ["Value", "Transaction Value", "Total Value"])
    shares_col = _first_existing(df, ["Shares", "Shares Traded", "Transaction Shares"])

    buy_re = re.compile(r"\b(purchase|purchased|buy|bought|open market purchase|acquisition|köp|kop)\b", re.I)
    sell_re = re.compile(r"\b(sale|sold|sell|disposition|försälj|forsalj)\w*\b", re.I)
    exclude_re = re.compile(r"\b(option|award|grant|gift|conversion|exercise|vesting|restricted stock)\b", re.I)

    buys: list[int] = []
    sells: list[int] = []
    for pos, (_, row) in enumerate(df.iterrows()):
        text = str(row.get(tx_col, "") if tx_col else "").strip()
        if not text or exclude_re.search(text):
            continue
        if buy_re.search(text):
            buys.append(pos)
        elif sell_re.search(text):
            sells.append(pos)

    # When Yahoo supplies a simple "Shares" direction without transaction text we
    # deliberately do not infer buy/sell. Ambiguity stays missing.
    buy_df = df.iloc[buys] if buys else df.iloc[0:0]
    if person_col and not buy_df.empty:
        buyers = buy_df[person_col].astype(str).str.strip().replace("", np.nan).dropna().nunique()
    else:
        buyers = 0

    buy_value = np.nan
    if value_col and not buy_df.empty:
        vals = pd.to_numeric(buy_df[value_col], errors="coerce").abs().dropna()
        if not vals.empty:
            buy_value = float(vals.sum())

    cluster = bool(len(buy_df) >= 2 and buyers >= 2)
    strong = bool(cluster and (buyers >= 3 or len(buy_df) >= 4) and len(sells) <= len(buy_df))
    if strong:
        explanation = f"{buyers} olika insiders har gjort {len(buy_df)} verifierbara köp senaste {lookback_days} dagarna"
    elif cluster:
        explanation = f"{buyers} olika insiders har gjort {len(buy_df)} verifierbara köp senaste {lookback_days} dagarna"
    elif len(buy_df):
        explanation = f"{len(buy_df)} verifierbart insiderköp, men inget oberoende köpkluster ännu"
    else:
        explanation = "Ingen verifierbar öppen-marknads-köpkluster i tillgängliga insiderdata"

    return {
        **base,
        "Insider köp antal": int(len(buy_df)),
        "Insider köpare antal": int(buyers),
        "Insider sälj antal": int(len(sells)),
        "Insider köp värde": buy_value,
        "Insider kluster": cluster,
        "Insider starkt kluster": strong,
        "Insider förklaring": explanation,
    }


def build_capital_allocation_insider_radar(
    cashflow: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    insider_transactions: pd.DataFrame | None,
    snapshot: dict[str, Any] | pd.Series | None = None,
    as_of: Any | None = None,
) -> dict[str, Any]:
    """Combine capital allocation and insider evidence into a no-score radar."""
    snap = snapshot if snapshot is not None else {}
    cap = build_capital_allocation_metrics(cashflow, balance, snap)
    ins = analyze_insider_cluster(insider_transactions, as_of=as_of)

    positives: list[str] = []
    warnings: list[str] = []
    buyback_yield = _num(cap.get("Kapitalallokering återköpsyield"))
    issuance_yield = _num(cap.get("Kapitalallokering emissionsyield"))
    debt_change = _num(cap.get("Kapitalallokering skuldtrend"))
    valuation = _num(snap.get("Värdering") if hasattr(snap, "get") else np.nan)
    debt_equity = _num(snap.get("Skuld/eget kapital") if hasattr(snap, "get") else np.nan)
    sector = str(snap.get("Sektor", "") if hasattr(snap, "get") else "").lower()
    financial = any(x in sector for x in ["financial", "bank", "finans", "insurance", "försäkring"])

    buyback_support = False
    if np.isfinite(buyback_yield):
        if buyback_yield >= 0.01 and (not np.isfinite(valuation) or valuation >= 45):
            buyback_support = True
            positives.append(f"nettoåterköp motsvarar cirka {buyback_yield:.1%} av börsvärdet")
        elif buyback_yield <= -0.02:
            warnings.append("nyemission/aktieutgivning överstiger observerade återköp tydligt")

    debt_support = False
    if np.isfinite(debt_change):
        if debt_change <= -0.10:
            debt_support = True
            positives.append("skuld/nettoskuld har minskat tydligt")
        elif debt_change >= 0.25:
            warnings.append("skuld/nettoskuld har ökat tydligt")

    if bool(ins.get("Insider kluster")):
        positives.append(ins.get("Insider förklaring", "flera insiders har köpt"))
    if _num(ins.get("Insider sälj antal")) >= 3 and not bool(ins.get("Insider kluster")):
        warnings.append("flera verifierbara insiderförsäljningar utan köpkluster")

    dilution_veto = bool(np.isfinite(issuance_yield) and issuance_yield >= 0.03 and not buyback_support)
    leverage_veto = bool((not financial) and np.isfinite(debt_equity) and debt_equity > 250 and not debt_support)
    candidate = bool(
        (buyback_support or debt_support or bool(ins.get("Insider kluster")))
        and not dilution_veto
        and not leverage_veto
    )
    strong = bool(
        candidate
        and sum([buyback_support, debt_support, bool(ins.get("Insider kluster"))]) >= 2
    )

    if dilution_veto:
        status = "Ägarutspädning väger tyngre"
    elif leverage_veto:
        status = "Positiv ägarsignal men hög skuldsättning"
    elif strong:
        status = "Flera ägarvänliga signaler"
    elif bool(ins.get("Insider kluster")):
        status = "Insiderköp i kluster"
    elif buyback_support:
        status = "Meningsfulla nettoåterköp"
    elif debt_support:
        status = "Tydlig skuldneddragning"
    elif warnings:
        status = "Kapitalallokering kräver försiktighet"
    else:
        status = "Ingen tydlig ägarsignal"

    explanation = "; ".join(positives[:3]) if positives else "Ingen verifierad owner-signal stark nog för discovery-fördel."
    if warnings:
        explanation += (". " if explanation else "") + "Varning: " + "; ".join(warnings[:2])

    return {
        **cap,
        **ins,
        "Ägarsignal status": status,
        "Ägarsignal kandidat": candidate,
        "Ägarsignal stark": strong,
        "Ägarsignal positiva": positives,
        "Ägarsignal varningar": warnings,
        "Ägarsignal förklaring": explanation,
    }


def select_owner_signal_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    """Select at most a tiny number of owner-signal candidates deterministically."""
    if df is None or df.empty or quota <= 0 or "Ägarsignal kandidat" not in df.columns:
        return []
    work = df[df["Ägarsignal kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__strong"] = work.get("Ägarsignal stark", False)
    work["__strong"] = pd.Series(work["__strong"], index=work.index).fillna(False).astype(int)
    work["__cluster"] = work.get("Insider kluster", False)
    work["__cluster"] = pd.Series(work["__cluster"], index=work.index).fillna(False).astype(int)
    work["__buyers"] = pd.to_numeric(work.get("Insider köpare antal"), errors="coerce").fillna(-1)
    work["__buyback"] = pd.to_numeric(work.get("Kapitalallokering återköpsyield"), errors="coerce").fillna(-999)
    work["__debt"] = pd.to_numeric(work.get("Kapitalallokering skuldtrend"), errors="coerce").fillna(999)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(
        ["__strong", "__cluster", "__buyers", "__buyback", "__debt", "__ticker"],
        ascending=[False, False, False, False, True, True],
        kind="mergesort",
    )
    return [(idx, "Ägarsignal") for idx in work.head(quota).index]
