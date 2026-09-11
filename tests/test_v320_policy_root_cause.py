import json
import pandas as pd

from policy_root_cause_diagnostics import (
    strictness_diagnostic,
    filtered_winner_diagnostic,
    regime_miss_diagnostics,
    data_diagnostic,
    policy_root_cause_summary,
)


def sample(n=20, kept=3, filtered_return=0.10):
    rows=[]
    for i in range(n):
        rows.append({
            "_target": True,
            "_requirement": i < kept,
            "return_pct": 0.02 if i < kept else filtered_return,
            "_snap": {"Marknadsläge":"SVAG", "Short Momentum":75, "Short Catalyst":70, "PIT Complete":True},
        })
    return pd.DataFrame(rows)


def test_strictness_flags_very_high_filter_rate():
    r = strictness_diagnostic(sample(20, kept=2))
    assert r["Status"] == "Stark kandidat"
    assert "90%" in r["Detalj"]


def test_filtered_winners_can_be_root_cause_candidate():
    r = filtered_winner_diagnostic(sample(20, kept=8, filtered_return=0.10))
    assert r["Status"] == "Stark kandidat"
    assert "starka vinnare" in r["Detalj"]


def test_regime_diagnostic_is_within_frozen_regime():
    rows=[]
    for i in range(16):
        regime="SVAG" if i < 8 else "MYCKET SVAG"
        rows.append({"_target":True,"_requirement":False,"return_pct":0.10 if regime=="SVAG" else -0.03,"_snap":{"Marknadsläge":regime}})
    out=regime_miss_diagnostics(pd.DataFrame(rows))
    assert any(r["Diagnostisk kandidat"] == "Filtreringsproblem i SVAG" and r["Status"] == "Stark kandidat" for r in out)
    assert any(r["Diagnostisk kandidat"] == "Filtreringsproblem i MYCKET SVAG" for r in out)


def test_data_diagnostic_flags_low_pit_coverage():
    class Spec:
        target = staticmethod(lambda s: True)
    rec=pd.DataFrame({"captured_at":["2026-09-07T00:00:00Z"]*20,"horizon_type":["short"]*20,"snapshot_json":[json.dumps({"PIT Complete": i < 10}) for i in range(20)]})
    event={"effective_at":"2026-09-06T00:00:00Z"}
    r=data_diagnostic(rec,event,Spec())
    assert r["Status"] == "Stark kandidat"
    assert "50%" in r["Detalj"]


def test_summary_never_auto_changes_policy():
    t=pd.DataFrame([{"Område":"X","Diagnostisk kandidat":"Y","Status":"Stark kandidat","N":10,"Detalj":"z"}])
    s=policy_root_cause_summary(t)
    assert s["status"] == "Stark kandidat hittad"
    assert s["automatic_change"] is False


def test_v320_is_current_version_and_ui_present():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert 'Policy Root Cause Diagnostics' in app
