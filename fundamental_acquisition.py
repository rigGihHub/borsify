from __future__ import annotations
"""Fundamental-data acquisition and persistent cache boundary for Borsify."""

from datetime import datetime
from pathlib import Path
from typing import Any
import math
import importlib

import numpy as np

from data_errors import classify_data_error, format_error
from resilience import call_with_resilience

from fundamental_cache import (
    get_cached_fundamentals,
    put_cached_fundamentals,
    CACHE_MAX_AGE_HOURS,
)


def _yf():
    return importlib.import_module("yfinance")


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _safe_info(ticker: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    health={"source":"Yahoo Finance via yfinance","status":"OK","method":"","errors":[],"attempts":{},"circuits_open":[]}

    value,res=call_with_resilience(
        lambda: ticker.get_info(),
        provider_key="yahoo:fundamental_get_info", context="fundamental:get_info",
    )
    health["attempts"]["get_info"]=res["attempts"]
    if res["ok"] and isinstance(value,dict):
        health["method"]="get_info"
        return value,health
    if not res["ok"]:
        err=res["error"] or {"type":"CircuitOpen","retryable":True}
        health["errors"].append(format_error(err))
        if res["circuit_open"]:
            health["circuits_open"].append("get_info")
    else:
        health["errors"].append("get_info:non_dict")

    value,res=call_with_resilience(
        lambda: ticker.info,
        provider_key="yahoo:fundamental_info", context="fundamental:info",
    )
    health["attempts"]["info"]=res["attempts"]
    if res["ok"] and isinstance(value,dict):
        health["method"]="info"
        health["status"]="PARTIAL" if health["errors"] else "OK"
        return value,health
    if not res["ok"]:
        err=res["error"] or {"type":"CircuitOpen","retryable":True}
        health["errors"].append(format_error(err))
        if res["circuit_open"]:
            health["circuits_open"].append("info")
    else:
        health["errors"].append("info:non_dict")

    health["status"]="ERROR"
    return {},health


def fetch_fundamentals(
    symbol: str,
    db_path: str | Path,
    major_currency_fn,
    max_age_hours: int = CACHE_MAX_AGE_HOURS,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return frozen fundamental payload plus structured source/cache health."""
    cached=get_cached_fundamentals(db_path,symbol,max_age_hours)
    if cached is not None:
        payload=dict(cached)
        payload["_Fundamental cache"]="beständig cache"
        return payload,{
            "source":"persistent fundamentals cache",
            "status":"OK",
            "cache":"HIT",
            "symbol":symbol,
            "errors":[],
        }

    health={
        "source":"Yahoo Finance via yfinance",
        "status":"OK",
        "cache":"MISS",
        "symbol":symbol,
        "errors":[],
    }
    ticker, _ticker_res = call_with_resilience(
        lambda: _yf().Ticker(symbol),
        provider_key="yahoo:fundamental_ticker", context="fundamental:ticker",
    )
    health["attempts"]=_ticker_res["attempts"]
    health["circuit_open"]=_ticker_res["circuit_open"]
    if not _ticker_res["ok"]:
        _err=_ticker_res["error"] or {"type":"CircuitOpen","retryable":True}
        health["status"]="CIRCUIT_OPEN" if _ticker_res["circuit_open"] else "ERROR"
        health["error_type"]=_err["type"]
        health["retryable"]=bool(_err.get("retryable"))
        health["classified_error"]=format_error(_err)
        health["errors"].append(f"ticker:{_err.get('detail') or _err.get('type')}")
        return {
            "Namn":symbol,"Sektor":"Okänd","Bransch":"Okänd","Valuta":"SEK",
            "Finansiell valuta":"SEK","Fundamental hämtad":datetime.now().isoformat(timespec="seconds"),
            "_Fundamental cache":"fel",
        },health

    info,info_health=_safe_info(ticker)
    health["info_method"]=info_health.get("method","")
    health["errors"].extend(info_health.get("errors",[]))
    if info_health.get("status")=="ERROR":
        health["status"]="ERROR"
    elif info_health.get("status")=="PARTIAL":
        health["status"]="PARTIAL"

    market_cap,fcf,target=_num(info.get("marketCap")),_num(info.get("freeCashflow")),_num(info.get("targetMeanPrice"))
    quote_currency=info.get("currency") or "SEK"
    payload={
        "Namn":info.get("shortName") or info.get("longName") or symbol,
        "Sektor":info.get("sector") or "Okänd",
        "Bransch":info.get("industry") or "Okänd",
        "Valuta":quote_currency,
        "Finansiell valuta":info.get("financialCurrency") or major_currency_fn(quote_currency),
        "Börsvärde lokal mdr":market_cap/1e9 if np.isfinite(market_cap) else np.nan,
        "Börsvärde BSEK":market_cap/1e9 if np.isfinite(market_cap) else np.nan,
        "P/E":_num(info.get("trailingPE")),
        "Forward P/E":_num(info.get("forwardPE")),
        "P/B":_num(info.get("priceToBook")),
        "EV/EBITDA":_num(info.get("enterpriseToEbitda")),
        "FCF-yield":fcf/market_cap if np.isfinite(fcf) and np.isfinite(market_cap) and market_cap>0 else np.nan,
        "ROE":_num(info.get("returnOnEquity")),
        "Vinstmarginal":_num(info.get("profitMargins")),
        "Skuld/eget kapital":_num(info.get("debtToEquity")),
        "Omsättningstillväxt":_num(info.get("revenueGrowth")),
        "Vinsttillväxt":_num(info.get("earningsGrowth")),
        "Direktavkastning":_num(info.get("dividendYield")),
        "Utdelningsandel":_num(info.get("payoutRatio")),
        "Analytikermål":target,
        "Rekommendation":info.get("recommendationKey") or "",
        "Antal analytiker":_num(info.get("numberOfAnalystOpinions")),
        "_Raw marketCap":market_cap,
        "_Raw freeCashflow":fcf,
        "_Raw totalDebt":_num(info.get("totalDebt")),
        "_Raw totalRevenue":_num(info.get("totalRevenue")),
        "_Raw netIncome":_num(info.get("netIncomeToCommon")),
        "Fundamental hämtad":datetime.now().isoformat(timespec="seconds"),
        "_Fundamental cache":"Yahoo",
    }
    # Persist only successful/partial vendor responses; never cache a total acquisition error.
    if health["status"]!="ERROR":
        try:
            to_cache=dict(payload)
            to_cache.pop("_Fundamental cache",None)
            put_cached_fundamentals(db_path,symbol,to_cache)
        except Exception as exc:
            health["status"]="PARTIAL"
            _err=classify_data_error(exc,context="fundamental:cache_write")
            health["errors"].append(format_error(_err))
    return payload,health
