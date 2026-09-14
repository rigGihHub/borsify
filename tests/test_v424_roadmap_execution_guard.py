import pandas as pd
from roadmap_execution_guard import build_execution_plan,next_safe_work_item,production_change_allowed

def test_validation_work_has_evidence_gate():
    r=pd.DataFrame([{"Utvecklingsspår":"Granska signal","Kategori":"MODEL_VALIDATION"}])
    p=build_execution_plan(r)
    assert "PIT-facit" in p.iloc[0]["Definition of done"]
    assert "BLOCKERAD" in p.iloc[0]["Produktionsändring"]

def test_data_reliability_requires_source_health():
    r=pd.DataFrame([{"Utvecklingsspår":"Fixa data","Kategori":"DATA_RELIABILITY"}])
    assert "source health" in build_execution_plan(r).iloc[0]["Definition of done"]

def test_evidence_gate_forbids_backfill():
    r=pd.DataFrame([{"Utvecklingsspår":"Bygg facit","Kategori":"EVIDENCE"}])
    assert "backfill" in build_execution_plan(r).iloc[0]["Definition of done"]

def test_module_cannot_approve_production_change():
    assert production_change_allowed(pd.DataFrame()) is False

def test_next_safe_item_is_first():
    r=pd.DataFrame([{"Utvecklingsspår":"A","Kategori":"REVIEW"},{"Utvecklingsspår":"B","Kategori":"REVIEW"}])
    assert next_safe_work_item(build_execution_plan(r))["work"]=="A"

def test_app_exposes_execution_plan():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.34.1"' in app
    assert "Säker genomförandeplan" in app
    assert "build_execution_plan(_risk_roadmap)" in app
