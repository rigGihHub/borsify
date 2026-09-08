import json
import pandas as pd
from news_event_memory import build_news_event_memory, apply_news_event_memory


def current():
    return {"Ticker":"ABC","News Surprise Primary Type":"Order/kontrakt","News Surprise Primary Direction":"positive","News Surprise Primary Title":"ABC wins new order","News Surprise Strength":2,"News Surprise Immediate Reaction":0.01,"News Surprise Five Day Reaction":0.02}

def rec(title, immediate, five):
    snap={"News Surprise Primary Type":"Order/kontrakt","News Surprise Primary Direction":"positive","News Surprise Primary Title":title,"News Surprise Strength":2,"News Surprise Immediate Reaction":immediate,"News Surprise Five Day Reaction":five}
    return {"symbol":"ABC","snapshot_json":json.dumps(snap)}

def test_requires_two_distinct_old_events():
    out=build_news_event_memory(current(),pd.DataFrame([rec("old one",.04,.06)]))
    assert out["News Event Memory N"] == 1
    assert out["News Event Memory Status"] == "Otillräcklig historik"

def test_same_company_same_type_median_and_gap():
    ledger=pd.DataFrame([rec("old one",.04,.06),rec("old two",.06,.08),rec("old one",.04,.06)])
    out=build_news_event_memory(current(),ledger)
    assert out["News Event Memory N"] == 2
    assert abs(out["News Event Memory Median Immediate"]-.05)<1e-9
    assert out["News Event Memory Status"] == "Historiskt större reaktion"
    assert out["News Event Memory Confidence"] == "Begränsad"

def test_negative_direction_is_normalized():
    c=current(); c.update({"News Surprise Primary Direction":"negative","News Surprise Primary Title":"warning now","News Surprise Immediate Reaction":-.01})
    rows=[]
    for title,r in [("warning old a",-.05),("warning old b",-.03)]:
        snap={"News Surprise Primary Type":"Order/kontrakt","News Surprise Primary Direction":"negative","News Surprise Primary Title":title,"News Surprise Strength":2,"News Surprise Immediate Reaction":r,"News Surprise Five Day Reaction":r}
        rows.append({"symbol":"ABC","snapshot_json":json.dumps(snap)})
    out=build_news_event_memory(c,pd.DataFrame(rows))
    assert abs(out["News Event Memory Median Immediate"]-.04)<1e-9
    assert out["News Event Memory Status"] == "Historiskt större reaktion"

def test_current_event_and_other_company_do_not_leak_into_history():
    rows=[rec("ABC wins new order",.20,.20),rec("old one",.04,.05),rec("old two",.03,.04)]
    rows.append({"symbol":"XYZ","snapshot_json":rows[1]["snapshot_json"]})
    out=build_news_event_memory(current(),pd.DataFrame(rows))
    assert out["News Event Memory N"] == 2

def test_apply_adds_memory_columns():
    frame=pd.DataFrame([current()]); ledger=pd.DataFrame([rec("old one",.04,.06),rec("old two",.06,.08)])
    out=apply_news_event_memory(frame,ledger)
    assert "News Event Memory Status" in out.columns
