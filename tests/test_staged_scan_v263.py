import numpy as np
import pandas as pd

from scan_pipeline import assess_price_history


def history(end, n=40):
    idx=pd.date_range(end=pd.Timestamp(end),periods=n,freq="B")
    close=np.linspace(90,100,n)
    return pd.DataFrame({
        "Open":close-.2,
        "High":close+1,
        "Low":close-1,
        "Close":close,
        "Volume":np.repeat(100_000,n),
    },index=idx)


def test_fresh_price_history_passes_before_fundamentals():
    now=pd.Timestamp("2026-09-03")
    result=assess_price_history(history(now),now=now)
    assert result["usable"] is True
    assert result["history_days"] >= 20


def test_stale_price_history_is_rejected_before_fundamentals():
    now=pd.Timestamp("2026-09-03")
    result=assess_price_history(history(now-pd.Timedelta(days=12)),now=now)
    assert result["usable"] is False
    assert "för gammalt" in result["reason"]


def test_short_history_is_rejected_before_fundamentals():
    now=pd.Timestamp("2026-09-03")
    result=assess_price_history(history(now,n=10),now=now)
    assert result["usable"] is False
    assert result["reason"]=="för kort kurshistorik"


def test_missing_close_is_rejected():
    result=assess_price_history(pd.DataFrame({"Open":[1,2,3]}),now="2026-09-03")
    assert result["usable"] is False
