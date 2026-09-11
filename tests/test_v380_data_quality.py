import json
import pandas as pd

from research_data_quality import data_quality_audit, apply_data_quality
from research_dossier_robustness import CHECK_PENDING


def _snap(post=True, coverage=.82, price_date="2026-01-01", fundamental="2026-01-01T08:00:00"):
    return json.dumps({
        "Post-report status": "POSITIV RAPPORTDRIFT" if post else "NEGATIV RAPPORTDRIFT",
        "Datatäckning": coverage,
        "Prisdatum": price_date,
        "Fundamental hämtad": fundamental,
    })


def _dataset(coverage=.82, stale=False, missing_ts=False, n=16):
    recs=[]; outs=[]
    for i in range(n):
        date=(pd.Timestamp("2026-01-02")+pd.Timedelta(days=i)).strftime("%Y-%m-%d")
        price=(pd.Timestamp(date)-pd.Timedelta(days=10 if stale else 1)).strftime("%Y-%m-%d")
        recs.append({
            "record_id":f"r{i}","symbol":f"S{i}","captured_date":date,"horizon_type":"long",
            "snapshot_json":_snap(True,coverage,price,"" if missing_ts else date+"T08:00:00")
        })
        outs.append({"record_id":f"r{i}","horizon":"1m","return_pct":.08})
    return pd.DataFrame(recs),pd.DataFrame(outs)


def test_data_quality_requires_mature_sample():
    recs,outs=_dataset(n=3)
    assert data_quality_audit("Post-Report Drift",recs,outs)["status"] == CHECK_PENDING


def test_data_quality_can_verify_good_frozen_inputs():
    recs,outs=_dataset()
    r=data_quality_audit("Post-Report Drift",recs,outs)
    assert r["status"] == "Datakvalitet verifierad"
    assert r["median_coverage"] >= .70
    assert r["fresh_price_share"] == 1.0
    assert r["fundamental_timestamp_share"] == 1.0


def test_data_quality_flags_stale_or_thin_inputs():
    recs,outs=_dataset(coverage=.40,stale=True,missing_ts=True)
    r=data_quality_audit("Post-Report Drift",recs,outs)
    assert r["status"] == "Datakvalitet ifrågasatt"
    assert r["median_coverage"] < .50
    assert r["fresh_price_share"] == 0.0


def test_partial_quality_keeps_blocker():
    recs,outs=_dataset()
    recs["snapshot_json"]=recs["snapshot_json"].map(lambda raw: json.dumps({"Post-report status":"POSITIV RAPPORTDRIFT"}))
    dossier=pd.DataFrame([{"Hypotes":"Post-Report Drift","Datakvalitet":"Ej verifierad","Blockerare":"datakvalitet","Nästa beslut":"Test."}])
    row=apply_data_quality(dossier,recs,outs).iloc[0]
    assert row["Datakvalitet"] == "Datakvalitet delvis verifierad"
    assert "datakvalitet" in row["Blockerare"]


def test_app_wires_data_quality_and_release_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "apply_data_quality(apply_cost_turnover(" in app
    assert "datakvalitet mäts nu direkt" in app
