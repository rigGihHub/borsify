import numpy as np
import pandas as pd
from idiosyncratic_volatility import idiosyncratic_volatility, apply_idiosyncratic_volatility


def _frame(rets):
    idx = pd.date_range("2025-01-01", periods=len(rets)+1, freq="B")
    px = 100*np.cumprod(np.r_[1.0, 1+np.asarray(rets)])
    return pd.DataFrame({"Close": px}, index=idx)


def test_market_driven_stock_has_low_residual_risk():
    rng=np.random.default_rng(7); b=rng.normal(0, .01, 180)
    s=1.1*b+rng.normal(0,.002,180)
    r=idiosyncratic_volatility(_frame(s),_frame(b))
    assert r["Idiosynkratisk volatilitet"] < .10
    assert r["Idiosynkratisk volatilitet status"] == "INGEN TYDLIG EXTRA RISK"


def test_company_specific_noise_is_flagged():
    rng=np.random.default_rng(9); b=rng.normal(0,.008,180)
    s=.7*b+rng.normal(0,.04,180)
    r=idiosyncratic_volatility(_frame(s),_frame(b))
    assert r["Idiosynkratisk volatilitet"] > .55
    assert r["Idiosynkratisk volatilitet status"] == "MYCKET HÖG BOLAGSSPECIFIK RISK"


def test_too_little_history_stays_missing():
    r=idiosyncratic_volatility(_frame([.01]*20),_frame([.01]*20))
    assert r["Idiosynkratisk volatilitet status"] == "FÖR LITE UNDERLAG"


def test_apply_preserves_rows():
    b=_frame([.001]*80); s=_frame([.002]*80)
    out=apply_idiosyncratic_volatility(pd.DataFrame([{"Ticker":"X","_history":s}]),b)
    assert len(out)==1 and "Idiosynkratisk volatilitet status" in out


def test_v303_wiring():
    app=open("app.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "apply_idiosyncratic_volatility" in app
    assert "Idiosynkratisk volatilitet status" in ledger
