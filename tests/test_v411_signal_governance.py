import pandas as pd
from signal_governance import nominate_signal_actions, governance_summary

def ev(sig,edge,n=25,ctl=25):
    return {"Signal":sig,"Signal N":n,"Control N":ctl,"Median edge":edge}

def test_promote_requires_mature_positive_edge():
    a=nominate_signal_actions(pd.DataFrame([ev("A",.05)]),pd.DataFrame())
    assert a.iloc[0].Action=="PROMOTE CANDIDATE"

def test_negative_mature_edge_becomes_retire_candidate():
    a=nominate_signal_actions(pd.DataFrame([ev("A",-.06)]),pd.DataFrame())
    assert a.iloc[0].Action=="RETIRE/DOWNWEIGHT CANDIDATE"

def test_small_sample_stays_observational():
    a=nominate_signal_actions(pd.DataFrame([ev("A",.30,5,5)]),pd.DataFrame())
    assert a.iloc[0].Action=="KEEP OBSERVING"

def test_high_redundancy_prioritises_merge_review():
    red=pd.DataFrame([{"Signal A":"A","Signal B":"B","Korrelation":.91,"Status":"x"}])
    a=nominate_signal_actions(pd.DataFrame([ev("A",.05)]),red)
    assert a.iloc[0].Action=="MERGE REVIEW"

def test_app_has_no_hardcoded_old_snapshot_date():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert '"2026-09-09"' not in app
    assert "_borsify_today()" in app
    assert "Signal Kill / Promote Candidates" in app
