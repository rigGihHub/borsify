from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def assess_price_history(hist: pd.DataFrame | None, now: Any=None) -> dict[str,Any]:
    """Hard price/history gate that can run before any fundamental request."""
    if hist is None or not isinstance(hist,pd.DataFrame) or hist.empty:
        return {"usable":False,"reason":"ingen kurshistorik","history_days":0,"price_date":"—"}

    if "Close" not in hist.columns:
        return {"usable":False,"reason":"stängningskurs saknas","history_days":0,"price_date":"—"}

    close=pd.to_numeric(hist["Close"],errors="coerce").dropna()
    if close.empty:
        return {"usable":False,"reason":"ingen giltig stängningskurs","history_days":0,"price_date":"—"}

    latest=float(close.iloc[-1])
    if not np.isfinite(latest) or latest <= 0:
        return {"usable":False,"reason":"saknar giltig aktuell kurs","history_days":len(close),"price_date":"—"}

    try:
        latest_ts=pd.Timestamp(close.index[-1])
        if latest_ts.tzinfo is not None:
            latest_ts=latest_ts.tz_localize(None)
        now_ts=pd.Timestamp(now) if now is not None else pd.Timestamp(datetime.now(timezone.utc)).tz_localize(None)
        if now_ts.tzinfo is not None:
            now_ts=now_ts.tz_localize(None)
        age=max(0,(now_ts.normalize()-latest_ts.normalize()).days)
        price_date=latest_ts.date().isoformat()
    except Exception:
        return {"usable":False,"reason":"saknar verifierbart kursdatum","history_days":len(close),"price_date":"—"}

    if len(close) < 20:
        return {
            "usable":False,
            "reason":"för kort kurshistorik",
            "history_days":len(close),
            "price_date":price_date,
            "price_age_days":age,
        }

    if age > 7:
        return {
            "usable":False,
            "reason":f"kursdatum är för gammalt ({age} dagar)",
            "history_days":len(close),
            "price_date":price_date,
            "price_age_days":age,
        }

    return {
        "usable":True,
        "reason":"",
        "history_days":len(close),
        "price_date":price_date,
        "price_age_days":age,
        "price":latest,
    }
