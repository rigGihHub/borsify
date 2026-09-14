import sqlite3, pandas as pd, numpy as np
from management_promise_delivery import parse_explicit_guidance, save_management_promises, promises_for_symbol, assess_promise_delivery

def test_no_generic_guidance_creates_promise():
    assert parse_explicit_guidance("Ingen explicit guidningsförändring","2026-01-01","AAA")==[]

def test_explicit_numeric_margin_guidance_is_frozen():
    p=parse_explicit_guidance("Bolaget höjer marginalguidningen till 18%","2026-01-01","AAA")
    assert len(p)==1 and p[0]["metric"]=="margin" and abs(p[0]["target"]-.18)<1e-9

def test_immutable_deduplicated_promise_memory():
    c=sqlite3.connect(":memory:")
    p=parse_explicit_guidance("raises EPS guidance to 12%","2026-01-01","AAA")
    save_management_promises(c,p,"2026-01-02"); save_management_promises(c,p,"2026-01-03")
    assert len(promises_for_symbol(c,"AAA"))==1

def test_delivery_not_claimed_without_matching_actual():
    p=pd.DataFrame(parse_explicit_guidance("raises margin guidance to 18%","2026-01-01","AAA"))
    r=assess_promise_delivery(p,{})
    assert r["Management promise verifierbara"]==0
    assert "inte verifierbar" in r["Management promise status"]

def test_delivery_rate_requires_actual_same_metric():
    p=pd.DataFrame(parse_explicit_guidance("raises margin guidance to 18%","2026-01-01","AAA"))
    r=assess_promise_delivery(p,{"margin":.20})
    assert r["Management promise verifierbara"]==1 and r["Management promise levererade"]==1

def test_app_exposes_feature_without_deal_conviction_weight():
    app=open("app.py",encoding="utf-8").read(); deal=open("deal_conviction.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert "Management Promise vs Delivery" in app
    assert "Management promise" not in deal
