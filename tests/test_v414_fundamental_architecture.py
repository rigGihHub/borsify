from pathlib import Path
import fundamental_acquisition as fa

def test_app_delegates_fundamentals():
    app=Path("app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "4.39.0"' in app
    assert "_fetch_fundamentals_source(symbol, DB_PATH, major_currency, CACHE_MAX_AGE_HOURS)" in app
    assert "get_cached_fundamentals(DB_PATH" not in app
    assert "put_cached_fundamentals(DB_PATH" not in app

def test_total_vendor_error_is_visible_and_not_cached(monkeypatch,tmp_path):
    class YF:
        class Ticker:
            def __init__(self,*a,**k): raise TimeoutError("x")
    monkeypatch.setattr(fa,"_yf",lambda:YF)
    monkeypatch.setattr(fa,"get_cached_fundamentals",lambda *a,**k:None)
    called=[]
    monkeypatch.setattr(fa,"put_cached_fundamentals",lambda *a,**k:called.append(1))
    payload,health=fa.fetch_fundamentals("AAA",tmp_path/"x.db",lambda x:x)
    assert health["status"]=="ERROR"
    assert called==[]
    assert "ticker:TimeoutError" in health["errors"]

def test_get_info_failure_can_fallback_to_info(monkeypatch,tmp_path):
    class T:
        def get_info(self): raise RuntimeError("bad")
        info={"shortName":"A","currency":"USD","marketCap":1000}
    class YF:
        Ticker=staticmethod(lambda s:T())
    monkeypatch.setattr(fa,"_yf",lambda:YF)
    monkeypatch.setattr(fa,"get_cached_fundamentals",lambda *a,**k:None)
    monkeypatch.setattr(fa,"put_cached_fundamentals",lambda *a,**k:None)
    payload,health=fa.fetch_fundamentals("AAA",tmp_path/"x.db",lambda x:x)
    assert payload["Namn"]=="A"
    assert health["status"]=="PARTIAL"
    assert health["info_method"]=="info"

def test_cache_hit_avoids_vendor(monkeypatch,tmp_path):
    monkeypatch.setattr(fa,"get_cached_fundamentals",lambda *a,**k:{"Namn":"Cached"})
    monkeypatch.setattr(fa,"_yf",lambda:(_ for _ in ()).throw(AssertionError("vendor called")))
    payload,health=fa.fetch_fundamentals("AAA",tmp_path/"x.db",lambda x:x)
    assert payload["Namn"]=="Cached"
    assert health["cache"]=="HIT"

def test_failure_transparency_uses_fundamental_source_status():
    from data_failure_transparency import assess_failure_transparency
    r=assess_failure_transparency({"Data Trust status":"GOTT UNDERLAG","Fundamental source status":"ERROR","Fundamental source errors":"ticker:TimeoutError"})
    assert "fundamental källa misslyckades" in r["Data Failure blockerare"]
