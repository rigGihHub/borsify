from __future__ import annotations

"""External market-data acquisition for Borsify.

This module owns direct yfinance/Yahoo access. It returns conservative fallbacks plus
structured source-health metadata so failures are observable by higher layers.
"""

from typing import Any
import math

import numpy as np
import pandas as pd

from data_errors import classify_data_error, classify_missing, format_error
from resilience import call_with_resilience
import importlib


def _yf():
    return importlib.import_module("yfinance")


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _pct_change(series: pd.Series, periods: int) -> float:
    try:
        s = pd.to_numeric(series, errors="coerce").dropna()
        if len(s) <= periods or periods <= 0:
            return np.nan
        old, new = float(s.iloc[-periods - 1]), float(s.iloc[-1])
        return new / old - 1 if math.isfinite(old) and old != 0 and math.isfinite(new) else np.nan
    except Exception:
        return np.nan


def bulk_price_history(symbols: tuple[str, ...]) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    if not symbols:
        return {}, {"source":"Yahoo Finance via yfinance","status":"EMPTY_REQUEST","error":"","requested":0,"returned":0}
    data, _res = call_with_resilience(
        lambda: _yf().download(
            tickers=list(symbols), period="1y", interval="1d", auto_adjust=True,
            actions=False, group_by="ticker", threads=True, progress=False, timeout=12,
        ),
        provider_key="yahoo:bulk_prices", context="bulk_price_history",
    )
    if not _res["ok"]:
        err=_res["error"] or {"type":"CircuitOpen","retryable":True}
        return {}, {
            "source":"Yahoo Finance via yfinance","status":"CIRCUIT_OPEN" if _res["circuit_open"] else "ERROR",
            "error":str(err.get("detail") or err.get("type") or ""),
            "error_type":err.get("type"),"error_detail":format_error(err),
            "retryable":bool(err.get("retryable")),"attempts":_res["attempts"],
            "circuit_open":_res["circuit_open"],"requested":len(symbols),"returned":0,
        }

    result: dict[str, pd.DataFrame] = {}
    if data is None or data.empty:
        err=classify_missing(context="bulk_price_history")
        return result, {"source":"Yahoo Finance via yfinance","status":"NO_DATA","error":format_error(err),"error_type":err["type"],"retryable":False,"requested":len(symbols),"returned":0}

    if len(symbols) == 1:
        frame = data.copy()
        if isinstance(frame.columns, pd.MultiIndex):
            try:
                frame = frame.xs(symbols[0], axis=1, level=0, drop_level=True)
            except Exception:
                try:
                    frame = frame.xs(symbols[0], axis=1, level=1, drop_level=True)
                except Exception:
                    pass
        result[symbols[0]] = frame
    elif isinstance(data.columns, pd.MultiIndex):
        level0 = set(map(str, data.columns.get_level_values(0)))
        level1 = set(map(str, data.columns.get_level_values(1)))
        for sym in symbols:
            try:
                if sym in level0:
                    result[sym] = data[sym].copy()
                elif sym in level1:
                    result[sym] = data.xs(sym, axis=1, level=1, drop_level=True).copy()
            except Exception:
                continue

    status = "OK" if len(result) == len(symbols) else "PARTIAL"
    return result, {
        "source":"Yahoo Finance via yfinance","status":status,"error":"",
        "requested":len(symbols),"returned":len(result),
        "missing":[s for s in symbols if s not in result],
        "attempts":_res["attempts"],"circuit_open":False,
    }


def single_price_history(symbol: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    hist, _res = call_with_resilience(
        lambda: _yf().Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True, actions=False),
        provider_key="yahoo:single_price", context="single_price_history",
    )
    if not _res["ok"]:
        err=_res["error"] or {"type":"CircuitOpen","retryable":True}
        return pd.DataFrame(), {
            "source":"Yahoo Finance via yfinance","status":"CIRCUIT_OPEN" if _res["circuit_open"] else "ERROR",
            "error":str(err.get("detail") or err.get("type") or ""),"error_type":err.get("type"),
            "error_detail":format_error(err),"retryable":bool(err.get("retryable")),
            "attempts":_res["attempts"],"circuit_open":_res["circuit_open"],"symbol":symbol,
        }
    if isinstance(hist, pd.DataFrame) and not hist.empty:
        return hist, {"source":"Yahoo Finance via yfinance","status":"OK","error":"","symbol":symbol,"attempts":_res["attempts"],"circuit_open":False}
    return pd.DataFrame(), {"source":"Yahoo Finance via yfinance","status":"NO_DATA","error":"","symbol":symbol,"attempts":_res["attempts"],"circuit_open":False}


def fx_rates_to_sek(
    currencies: tuple[str, ...],
    fx_symbols: dict[str, str],
    major_currency_fn,
) -> tuple[dict[str, float], dict[str, Any]]:
    needed = sorted({major_currency_fn(c) for c in currencies if major_currency_fn(c) != "SEK"})
    rates: dict[str, float] = {"SEK": 1.0}
    errors: dict[str, str] = {}
    missing_symbols: list[str] = []
    for currency in needed:
        symbol = fx_symbols.get(currency)
        if not symbol:
            missing_symbols.append(currency)
            continue
        hist, _res = call_with_resilience(
            lambda symbol=symbol: _yf().Ticker(symbol).history(period="5d", interval="1d", auto_adjust=True, actions=False),
            provider_key="yahoo:fx", context=f"fx:{currency}",
        )
        if not _res["ok"]:
            _err=_res["error"] or {"type":"CircuitOpen","retryable":True}
            errors[currency]=format_error(_err)
            continue
        if isinstance(hist, pd.DataFrame) and not hist.empty and "Close" in hist.columns:
            close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
            if not close.empty:
                rate = _num(close.iloc[-1])
                if np.isfinite(rate) and rate > 0:
                    rates[currency] = rate
                    continue
        errors[currency] = "NoData"
    missing = [c for c in needed if c not in rates]
    status = "OK" if not missing else ("PARTIAL" if len(rates) > 1 else "ERROR")
    return rates, {
        "source":"Yahoo Finance via yfinance","status":status,"error":errors,
        "requested":needed,"missing":missing,"missing_mapping":missing_symbols,
    }


def index_snapshot(symbol: str = "^OMXS30") -> tuple[dict[str, float], dict[str, Any]]:
    if not symbol:
        return {}, {"source":"Yahoo Finance via yfinance","status":"EMPTY_REQUEST","error":"","symbol":symbol}
    hist, _res = call_with_resilience(
        lambda: _yf().Ticker(symbol).history(period="1y", interval="1d", auto_adjust=True, actions=False),
        provider_key="yahoo:index", context="index_snapshot",
    )
    if not _res["ok"]:
        err=_res["error"] or {"type":"CircuitOpen","retryable":True}
        return {}, {
            "source":"Yahoo Finance via yfinance","status":"CIRCUIT_OPEN" if _res["circuit_open"] else "ERROR",
            "error":str(err.get("detail") or err.get("type") or ""),"error_type":err.get("type"),
            "error_detail":format_error(err),"retryable":bool(err.get("retryable")),
            "attempts":_res["attempts"],"circuit_open":_res["circuit_open"],"symbol":symbol,
        }
    if hist is None or hist.empty or "Close" not in hist.columns:
        return {}, {"source":"Yahoo Finance via yfinance","status":"NO_DATA","error":"","symbol":symbol,"attempts":_res["attempts"],"circuit_open":False}
    close = pd.to_numeric(hist["Close"], errors="coerce").dropna()
    if close.empty:
        return {}, {"source":"Yahoo Finance via yfinance","status":"NO_DATA","error":"","symbol":symbol,"attempts":_res["attempts"],"circuit_open":False}
    snap = {
        "index": _num(close.iloc[-1]),
        "daily": _pct_change(close, 1),
        "month": _pct_change(close, min(21, max(len(close)-1, 1))),
        "3m": _pct_change(close, min(63, max(len(close)-1, 1))),
        "6m": _pct_change(close, min(126, max(len(close)-1, 1))),
    }
    return snap, {"source":"Yahoo Finance via yfinance","status":"OK","error":"","symbol":symbol,"attempts":_res["attempts"],"circuit_open":False}


def deep_statements(symbol: str) -> dict[str, Any]:
    health: dict[str, Any] = {
        "source":"Yahoo Finance via yfinance",
        "symbol":symbol,
        "status":"OK",
        "errors":{},
        "error_types":{},
        "missing":[],
    }

    t, _ticker_res = call_with_resilience(
        lambda: _yf().Ticker(symbol),
        provider_key="yahoo:deep_ticker", context="deep:ticker",
    )
    if not _ticker_res["ok"]:
        err=_ticker_res["error"] or {"type":"CircuitOpen","retryable":True}
        return {
            "income":pd.DataFrame(),"cashflow":pd.DataFrame(),"balance":pd.DataFrame(),
            "quarterly_income":pd.DataFrame(),"quarterly_cashflow":pd.DataFrame(),"quarterly_balance":pd.DataFrame(),
            "error":err["type"],
            "source_health":{
                **health,
                "status":"CIRCUIT_OPEN" if _ticker_res["circuit_open"] else "ERROR",
                "errors":{"ticker":str(err.get("detail") or err.get("type") or "")},
                "error_types":{"ticker":err["type"]},
                "error_details":{"ticker":format_error(err)},
                "attempts":{"ticker":_ticker_res["attempts"]},
                "circuit_open":_ticker_res["circuit_open"],
            },
        }
    health["attempts"]={"ticker":_ticker_res["attempts"]}
    health["circuit_open"]=False

    def _frame(label: str, getter) -> pd.DataFrame:
        value, _res = call_with_resilience(
            getter,
            provider_key=f"yahoo:deep:{label}", context=f"deep:{label}",
        )
        health.setdefault("attempts", {})[label]=_res["attempts"]
        if not _res["ok"]:
            _err=_res["error"] or {"type":"CircuitOpen","retryable":True}
            health["errors"][label]=format_error(_err)
            health["error_types"][label]=_err["type"]
            if _res["circuit_open"]:
                health.setdefault("circuits_open", []).append(label)
            return pd.DataFrame()
        if isinstance(value, pd.DataFrame) and not value.empty:
            return value
        health["missing"].append(label)
        return pd.DataFrame()

    fast_info: dict[str, Any] = {}
    try:
        fi = t.fast_info
        for source_key, target_key in (("last_price","last_price"),("market_cap","market_cap")):
            try:
                value = fi.get(source_key) if hasattr(fi,"get") else getattr(fi,source_key)
                if value is not None:
                    fast_info[target_key] = value
            except Exception as exc:
                _err=classify_data_error(exc,context=f"deep:fast_info.{source_key}")
                health["errors"][f"fast_info.{source_key}"]=format_error(_err)
                health["error_types"][f"fast_info.{source_key}"]=_err["type"]
    except Exception as exc:
        _err=classify_data_error(exc,context="deep:fast_info")
        health["errors"]["fast_info"]=format_error(_err)
        health["error_types"]["fast_info"]=_err["type"]

    income = _frame("income", lambda: t.income_stmt)
    cashflow = _frame("cashflow", lambda: t.cashflow)
    balance = _frame("balance", lambda: t.balance_sheet)
    quarterly_income = _frame("quarterly_income", lambda: t.quarterly_income_stmt)
    quarterly_cashflow = _frame("quarterly_cashflow", lambda: t.quarterly_cashflow)
    quarterly_balance = _frame("quarterly_balance", lambda: t.quarterly_balance_sheet)

    def _analyst_frame(label: str, *names: str) -> pd.DataFrame:
        for name in names:
            try:
                value = getattr(t, name)
                if callable(value):
                    value = value()
                if isinstance(value, pd.DataFrame):
                    if not value.empty:
                        return value
            except Exception as exc:
                _err=classify_data_error(exc,context=f"deep:{label}.{name}")
                health["errors"][f"{label}.{name}"]=format_error(_err)
                health["error_types"][f"{label}.{name}"]=_err["type"]
        health["missing"].append(label)
        return pd.DataFrame()

    eps_trend = _analyst_frame("eps_trend","eps_trend","get_eps_trend")
    eps_revisions = _analyst_frame("eps_revisions","eps_revisions","get_eps_revisions")
    earnings_estimate = _analyst_frame("earnings_estimate","earnings_estimate","get_earnings_estimate")
    earnings_history = _analyst_frame("earnings_history","earnings_history","get_earnings_history")
    insider_transactions = _analyst_frame("insider_transactions","insider_transactions","get_insider_transactions")
    recommendation_summary = _analyst_frame("recommendations","recommendations","recommendations_summary","get_recommendations")
    upgrades_downgrades = _analyst_frame("upgrades_downgrades","upgrades_downgrades","get_upgrades_downgrades")

    analyst_price_targets: dict[str, Any] | pd.Series = {}
    try:
        analyst_price_targets = t.analyst_price_targets
        if callable(analyst_price_targets):
            analyst_price_targets = analyst_price_targets()
        if not isinstance(analyst_price_targets,(dict,pd.Series)):
            analyst_price_targets = {}
            health["missing"].append("analyst_price_targets")
    except Exception as exc:
        _err=classify_data_error(exc,context="deep:analyst_price_targets")
        health["errors"]["analyst_price_targets"]=format_error(_err)
        health["error_types"]["analyst_price_targets"]=_err["type"]

    price_history = _frame("price_history", lambda: t.history(period="6mo", interval="1d", auto_adjust=False))

    earnings_date = None
    try:
        cal = t.calendar
        if isinstance(cal, dict):
            earnings_date = cal.get("Earnings Date") or cal.get("EarningsDate")
            if isinstance(earnings_date,(list,tuple)) and earnings_date:
                earnings_date = earnings_date[0]
        elif isinstance(cal,pd.DataFrame) and not cal.empty:
            for key in ["Earnings Date","EarningsDate"]:
                if key in cal.index:
                    earnings_date = cal.loc[key].iloc[0]
                    break
    except Exception as exc:
        _err=classify_data_error(exc,context="deep:calendar")
        health["errors"]["calendar"]=format_error(_err)
        health["error_types"]["calendar"]=_err["type"]

    catalyst_news = []
    try:
        for item in (t.news or [])[:6]:
            content = item.get("content", item) if isinstance(item,dict) else {}
            title = content.get("title") if isinstance(content,dict) else None
            if not title and isinstance(item,dict):
                title = item.get("title")
            link = None
            if isinstance(content,dict):
                canonical = content.get("canonicalUrl") or content.get("clickThroughUrl")
                if isinstance(canonical,dict):
                    link = canonical.get("url")
                elif isinstance(canonical,str):
                    link = canonical
            if not link and isinstance(item,dict):
                link = item.get("link")
            if title:
                published_at = content.get("pubDate") or content.get("displayTime") if isinstance(content,dict) else None
                provider = None
                if isinstance(content,dict):
                    provider_obj = content.get("provider")
                    if isinstance(provider_obj,dict):
                        provider = provider_obj.get("displayName") or provider_obj.get("name")
                if not published_at and isinstance(item,dict):
                    published_at = item.get("providerPublishTime") or item.get("pubDate")
                catalyst_news.append({"title":str(title),"link":link,"published_at":published_at,"provider":provider})
    except Exception as exc:
        _err=classify_data_error(exc,context="deep:news")
        health["errors"]["news"]=format_error(_err)
        health["error_types"]["news"]=_err["type"]

    critical = ["income","cashflow","balance","quarterly_income","quarterly_cashflow","quarterly_balance"]
    critical_missing = [x for x in critical if x in health["missing"] or x in health["errors"]]
    if len(critical_missing) >= 4:
        health["status"] = "DEGRADED"
    elif health["errors"] or health["missing"]:
        health["status"] = "PARTIAL"

    error = ""
    if health["status"] == "DEGRADED":
        error = "DeepDataDegraded"

    return {
        "income":income,"cashflow":cashflow,"balance":balance,
        "quarterly_income":quarterly_income,"quarterly_cashflow":quarterly_cashflow,
        "quarterly_balance":quarterly_balance,
        "eps_trend":eps_trend,"eps_revisions":eps_revisions,
        "earnings_estimate":earnings_estimate,"earnings_history":earnings_history,
        "insider_transactions":insider_transactions,
        "recommendation_summary":recommendation_summary,"upgrades_downgrades":upgrades_downgrades,
        "analyst_price_targets":analyst_price_targets,
        "price_history":price_history,
        "catalyst_events":{"earnings":earnings_date,"news":catalyst_news},
        "fast_info":fast_info,
        "external_verification_status":"SAKNAS",
        "source_health":health,
        "error":error,
    }
