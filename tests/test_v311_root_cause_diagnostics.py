import json
import pandas as pd

from root_cause_diagnostics import prepare_root_cause_sample, root_cause_table, root_cause_summary

FIELDS = {
    "Short Relative Strength": 60,
    "Short Trend": 60,
    "Short Momentum": 60,
    "Short Participation": 60,
    "Short Revisions": 60,
    "Short Catalyst": 60,
}


def _frames(n=30, signal_break=False, bad_sector=False, pit_drop=False):
    recs=[]; outs=[]
    base=pd.Timestamp("2025-01-01")
    for i in range(n):
        recent=i >= n-12
        snap={"PIT Complete": not (pit_drop and recent), "Marknadsläge": "Normal", "Sektor":"Tech" if not (bad_sector and recent) else "Problemsektor", **FIELDS}
        if signal_break and recent:
            # Reverse the signal ordering vs outcome so correlation deteriorates.
            snap["Short Momentum"] = 90 - i
        ret=(i % 12)/100
        if recent and signal_break:
            ret=(i-(n-12))/100
        if recent and bad_sector:
            ret=-0.10
        recs.append({"record_id":f"r{i}","symbol":f"S{i}","captured_date":(base+pd.Timedelta(days=i*40)).date().isoformat(),"horizon_type":"short","score":60+i%20,"snapshot_json":json.dumps(snap),"market":"Sverige","model_version":"3.11.0"})
        outs.append({"record_id":f"r{i}","symbol":f"S{i}","horizon":"1m","return_pct":ret})
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_prepare_uses_independent_point_in_time_rows():
    recs, outs=_frames()
    data=prepare_root_cause_sample(recs, outs, "1m")
    assert len(data) == 30
    assert "_sector" in data.columns
    assert "_sig_Momentum" in data.columns


def test_root_cause_detects_pit_quality_drop():
    recs, outs=_frames(pit_drop=True)
    table=root_cause_table(recs, outs, "1m")
    assert ((table["Område"]=="Data") & (table["Kandidat"]=="PIT-kompletthet")).any()


def test_root_cause_detects_concentrated_sector_weakness():
    recs, outs=_frames(bad_sector=True)
    table=root_cause_table(recs, outs, "1m")
    assert ((table["Område"]=="Sektor") & (table["Kandidat"]=="Problemsektor")).any()


def test_summary_never_claims_causality():
    table=pd.DataFrame([{"Område":"Signal","Kandidat":"Momentum","Styrka":"Stark kandidat","Förklaring":"x"}])
    result=root_cause_summary(table, 30)
    assert result["status"] == "Rotorsakskandidater hittade"
    assert "inte bevis" in result["text"]


def test_summary_waits_for_minimum_history():
    assert root_cause_summary(pd.DataFrame(), 10)["status"] == "Vänta"


def test_v311_ui_and_version():
    app=open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Root Cause Diagnostics · varför kan modellen ha försämrats?" in app
    assert "aldrig bevisad kausalitet" in app
