from pathlib import Path
import pandas as pd
import data_acquisition as da

def test_app_wrappers_delegate_to_data_acquisition():
    app=Path("app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.38.1"' in app
    assert "_deep_statements_source(symbol)" in app
    assert "_bulk_price_history_source(symbols)" in app
    assert "_fx_rates_to_sek_source(currencies, FX_TO_SEK_SYMBOLS, major_currency)" in app

def test_app_no_longer_owns_direct_deep_yfinance_logic():
    app=Path("app.py").read_text(encoding="utf-8")
    lines=app.splitlines()
    start=next(i for i,line in enumerate(lines) if line.startswith("def fetch_deep_statements("))
    body="\n".join(lines[start:start+6])
    assert "yf.Ticker" not in body
    assert "_deep_statements_source(symbol)" in body

def test_deep_source_failure_returns_structured_health(monkeypatch):
    class Boom:
        def __init__(self,*a,**k):
            raise RuntimeError("x")
    class YF:
        Ticker=Boom
    monkeypatch.setattr(da,"_yf",lambda:YF)
    r=da.deep_statements("AAA")
    assert r["source_health"]["status"]=="ERROR"
    assert r["source_health"]["errors"]["ticker"]=="RuntimeError"

def test_bulk_source_failure_is_visible(monkeypatch):
    def boom(*a,**k):
        raise TimeoutError("x")
    class YF:
        download=staticmethod(boom)
    monkeypatch.setattr(da,"_yf",lambda:YF)
    data,health=da.bulk_price_history(("AAA","BBB"))
    assert data=={}
    assert health["status"]=="ERROR"
    assert health["error"]=="TimeoutError"

def test_partial_deep_source_does_not_invent_missing_frames(monkeypatch):
    class T:
        fast_info={}
        income_stmt=pd.DataFrame()
        cashflow=pd.DataFrame()
        balance_sheet=pd.DataFrame()
        quarterly_income_stmt=pd.DataFrame()
        quarterly_cashflow=pd.DataFrame()
        quarterly_balance_sheet=pd.DataFrame()
        eps_trend=pd.DataFrame()
        eps_revisions=pd.DataFrame()
        earnings_estimate=pd.DataFrame()
        earnings_history=pd.DataFrame()
        insider_transactions=pd.DataFrame()
        recommendations=pd.DataFrame()
        recommendations_summary=pd.DataFrame()
        upgrades_downgrades=pd.DataFrame()
        analyst_price_targets={}
        calendar={}
        news=[]
        def history(self,*a,**k): return pd.DataFrame()
    class YF:
        Ticker=staticmethod(lambda symbol:T())
    monkeypatch.setattr(da,"_yf",lambda:YF)
    r=da.deep_statements("AAA")
    assert r["source_health"]["status"]=="DEGRADED"
    assert "quarterly_income" in r["source_health"]["missing"]
    assert r["quarterly_income"].empty
