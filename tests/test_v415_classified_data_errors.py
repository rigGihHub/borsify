import pandas as pd
import data_errors as de
import data_acquisition as da
import fundamental_acquisition as fa

def test_timeout_classification():
    r=de.classify_data_error(TimeoutError("timed out"),context="x")
    assert r["type"]=="Timeout" and r["retryable"] is True

def test_rate_limit_classification():
    r=de.classify_data_error(RuntimeError("429 Too Many Requests"))
    assert r["type"]=="RateLimited" and r["retryable"] is True

def test_schema_change_classification():
    r=de.classify_data_error(KeyError("new_field"))
    assert r["type"]=="SchemaChanged" and r["retryable"] is False

def test_bulk_timeout_surfaces_stable_error_type(monkeypatch):
    class YF:
        @staticmethod
        def download(*a,**k): raise TimeoutError("slow")
    monkeypatch.setattr(da,"_yf",lambda:YF)
    data,h=da.bulk_price_history(("AAA",))
    assert data=={}
    assert h["error_type"]=="Timeout"
    assert h["retryable"] is True

def test_deep_schema_error_is_recorded_per_component(monkeypatch):
    class T:
        fast_info={}
        @property
        def income_stmt(self): raise KeyError("schema")
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
        Ticker=staticmethod(lambda s:T())
    monkeypatch.setattr(da,"_yf",lambda:YF)
    r=da.deep_statements("AAA")
    assert r["source_health"]["error_types"]["income"]=="SchemaChanged"

def test_fundamental_timeout_surfaces_classified_error(monkeypatch,tmp_path):
    class YF:
        class Ticker:
            def __init__(self,*a,**k): raise TimeoutError("slow")
    monkeypatch.setattr(fa,"_yf",lambda:YF)
    monkeypatch.setattr(fa,"get_cached_fundamentals",lambda *a,**k:None)
    p,h=fa.fetch_fundamentals("AAA",tmp_path/"x.db",lambda x:x)
    assert h["error_type"]=="Timeout"
    assert h["retryable"] is True

def test_app_version_and_provenance_field():
    app=open("app.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.37.0"' in app
    assert "Deep source error types" in app
    assert '"Deep source error types"' in ledger
