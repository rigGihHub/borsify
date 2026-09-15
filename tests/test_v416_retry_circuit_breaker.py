import pandas as pd
import resilience as rs
import data_acquisition as da
import fundamental_acquisition as fa

def setup_function():
    rs.reset_circuit()

def test_retryable_timeout_retries_then_succeeds():
    calls=[]
    def f():
        calls.append(1)
        if len(calls)==1:
            raise TimeoutError("slow")
        return 7
    value,meta=rs.call_with_resilience(f,provider_key="x",context="x",max_attempts=2,base_delay_seconds=0,sleep_fn=lambda _:None)
    assert value==7
    assert meta["ok"] is True
    assert meta["attempts"]==2

def test_schema_changed_is_not_retried():
    calls=[]
    def f():
        calls.append(1)
        raise KeyError("schema")
    value,meta=rs.call_with_resilience(f,provider_key="x",context="x",max_attempts=3,base_delay_seconds=0,sleep_fn=lambda _:None)
    assert value is None
    assert meta["attempts"]==1
    assert meta["error"]["type"]=="SchemaChanged"

def test_circuit_opens_after_repeated_retryable_failures():
    def f(): raise TimeoutError("slow")
    for _ in range(2):
        rs.call_with_resilience(f,provider_key="x",context="x",max_attempts=2,base_delay_seconds=0,sleep_fn=lambda _:None)
    value,meta=rs.call_with_resilience(f,provider_key="x",context="x",max_attempts=2,base_delay_seconds=0,sleep_fn=lambda _:None)
    assert value is None
    assert meta["circuit_open"] is True
    assert meta["attempts"]==0

def test_bulk_timeout_retries_and_reports_attempts(monkeypatch):
    calls=[]
    class YF:
        @staticmethod
        def download(*a,**k):
            calls.append(1)
            if len(calls)==1: raise TimeoutError("slow")
            return pd.DataFrame({"Close":[1,2]})
    monkeypatch.setattr(da,"_yf",lambda:YF)
    data,h=da.bulk_price_history(("AAA",))
    assert h["attempts"]==2
    assert h["circuit_open"] is False
    assert "AAA" in data

def test_bulk_schema_error_does_not_retry(monkeypatch):
    calls=[]
    class YF:
        @staticmethod
        def download(*a,**k):
            calls.append(1); raise KeyError("schema")
    monkeypatch.setattr(da,"_yf",lambda:YF)
    data,h=da.bulk_price_history(("AAA",))
    assert len(calls)==1
    assert h["error_type"]=="SchemaChanged"

def test_fundamental_get_info_timeout_retries_before_info_fallback(monkeypatch,tmp_path):
    calls=[]
    class T:
        def get_info(self):
            calls.append(1)
            if len(calls)==1: raise TimeoutError("slow")
            return {"shortName":"A","currency":"SEK"}
        info={"shortName":"B","currency":"SEK"}
    class YF:
        Ticker=staticmethod(lambda s:T())
    monkeypatch.setattr(fa,"_yf",lambda:YF)
    monkeypatch.setattr(fa,"get_cached_fundamentals",lambda *a,**k:None)
    monkeypatch.setattr(fa,"put_cached_fundamentals",lambda *a,**k:None)
    p,h=fa.fetch_fundamentals("AAA",tmp_path/"x.db",lambda x:x)
    assert p["Namn"]=="A"
    assert h["info_method"]=="get_info"

def test_failure_transparency_marks_open_circuit():
    from data_failure_transparency import assess_failure_transparency
    r=assess_failure_transparency({"Data Trust status":"GOTT UNDERLAG","Fundamental circuit open":True})
    assert "circuit breaker" in r["Data Failure blockerare"]
    assert "BLOCKERAD" in r["Data Failure status"]

def test_app_version_and_frozen_resilience_provenance():
    app=open("app.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.0"' in app
    assert "Fundamental circuit open" in app
    assert '"Deep source circuits open"' in ledger
