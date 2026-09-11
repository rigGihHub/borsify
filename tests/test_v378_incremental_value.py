import json
import pandas as pd

from research_incremental_value import incremental_value, apply_incremental_value
from research_dossier_robustness import CHECK_PENDING


def _row(i, post_positive, eq_positive, momentum_positive=False):
    snap = {
        "Post-report status": "POSITIV RAPPORTDRIFT" if post_positive else "NEGATIV RAPPORTDRIFT",
        "Vinstkvalitet status": "STARK VINSTKVALITET" if eq_positive else "SVAG VINSTKVALITET",
        "12–1 momentum score": 70 if momentum_positive else 50,
    }
    return {
        "record_id": f"r{i}", "symbol": f"S{i}", "captured_date": f"2026-09-{(i%28)+1:02d}",
        "horizon_type": "long", "model_version": "3.81.0", "snapshot_json": json.dumps(snap),
    }


def test_incremental_value_requires_matched_background_strata():
    recs = pd.DataFrame([_row(i, True, True) for i in range(10)])
    outs = pd.DataFrame([{"record_id": f"r{i}", "horizon": "1m", "return_pct": .1} for i in range(10)])
    assert incremental_value("Post-Report Drift", recs, outs)["status"] == CHECK_PENDING


def test_incremental_value_finds_support_inside_same_other_signal_backgrounds():
    recs=[]; outs=[]; i=0
    # Two exact background strata: EQ positive and EQ negative. Each has 4 target+/4 target-.
    for eq in [True, False]:
        for target in [True]*4 + [False]*4:
            recs.append(_row(i, target, eq))
            outs.append({"record_id": f"r{i}", "horizon": "1m", "return_pct": .12 if target else -.02})
            i += 1
    result = incremental_value("Post-Report Drift", pd.DataFrame(recs), pd.DataFrame(outs))
    assert result["status"] == "Tydligt inkrementellt stöd"
    assert result["matched_strata"] == 2
    assert result["matched_cases"] == 16


def test_incremental_value_can_reject_apparent_signal_after_matching():
    recs=[]; outs=[]; i=0
    for eq in [True, False]:
        for target in [True]*4 + [False]*4:
            recs.append(_row(i, target, eq))
            outs.append({"record_id": f"r{i}", "horizon": "1m", "return_pct": -.05 if target else .08})
            i += 1
    result = incremental_value("Post-Report Drift", pd.DataFrame(recs), pd.DataFrame(outs))
    assert result["status"] == "Inget inkrementellt värde"


def test_apply_removes_incremental_blocker_only_when_measured():
    recs=[]; outs=[]; i=0
    for eq in [True, False]:
        for target in [True]*4 + [False]*4:
            recs.append(_row(i, target, eq))
            outs.append({"record_id": f"r{i}", "horizon": "1m", "return_pct": .1 if target else -.01})
            i += 1
    dossier=pd.DataFrame([{"Hypotes":"Post-Report Drift","Incrementellt värde":"Ej verifierad","Blockerare":"inkrementellt värde, kostnad/omsättning","Nästa beslut":"Test."}])
    out=apply_incremental_value(dossier,pd.DataFrame(recs),pd.DataFrame(outs)).iloc[0]
    assert out["Incrementellt värde"] == "Tydligt inkrementellt stöd"
    assert "inkrementellt värde" not in out["Blockerare"]
    assert "kostnad/omsättning" in out["Blockerare"]


def test_app_wires_incremental_value_and_release_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "apply_incremental_value(apply_dossier_robustness(build_review_dossiers(research_queue), recs, outs), recs, outs)" in app
    assert '"Incrementellt värde"' in app
