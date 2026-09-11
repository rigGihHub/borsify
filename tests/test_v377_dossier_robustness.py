import json
import pandas as pd

from research_dossier_robustness import regime_robustness, signal_overlap, apply_dossier_robustness, CHECK_PENDING


def _rec(i, regime, post_status, eq_status="STARK VINSTKVALITET"):
    return {
        "record_id": f"r{i}", "symbol": f"S{i}", "captured_date": f"2026-01-{(i%28)+1:02d}",
        "horizon_type": "long", "model_version": "3.77.0",
        "snapshot_json": json.dumps({"Marknadsläge": regime, "Post-report status": post_status, "Vinstkvalitet status": eq_status}),
    }


def test_regime_robustness_requires_multiple_mature_regimes():
    recs = pd.DataFrame([_rec(i, "Bull", "POSITIV RAPPORTDRIFT" if i < 5 else "NEGATIV RAPPORTDRIFT") for i in range(10)])
    outs = pd.DataFrame([{"record_id": f"r{i}", "horizon": "1m", "return_pct": .1 if i < 5 else -.05} for i in range(10)])
    assert regime_robustness("Post-Report Drift", recs, outs)["status"] == CHECK_PENDING


def test_regime_robustness_can_verify_same_direction_across_two_regimes():
    recs=[]; outs=[]; i=0
    for regime in ["Bull", "Bear"]:
        for positive in [True]*4 + [False]*4:
            recs.append(_rec(i, regime, "POSITIV RAPPORTDRIFT" if positive else "NEGATIV RAPPORTDRIFT"))
            outs.append({"record_id": f"r{i}", "horizon": "1m", "return_pct": .12 if positive else -.03})
            i += 1
    result = regime_robustness("Post-Report Drift", pd.DataFrame(recs), pd.DataFrame(outs))
    assert result["status"] == "Stöd i flera regimer"
    assert result["mature_regimes"] == 2


def test_signal_overlap_never_claims_verification_on_tiny_sample():
    recs = pd.DataFrame([_rec(i, "Bull", "POSITIV RAPPORTDRIFT") for i in range(5)])
    assert signal_overlap("Post-Report Drift", recs)["status"] == CHECK_PENDING


def test_signal_overlap_detects_high_overlap_from_frozen_snapshots():
    rows=[]
    for i in range(12):
        r=_rec(i, "Bull", "POSITIV RAPPORTDRIFT", "STARK VINSTKVALITET")
        rows.append(r)
    result=signal_overlap("Post-Report Drift", pd.DataFrame(rows))
    assert result["status"] == "Högt överlapp"
    assert result["partner"] == "Earnings Quality 2.0"


def test_apply_only_removes_blockers_when_check_is_measured():
    rows=[]; outs=[]; i=0
    for regime in ["Bull", "Bear"]:
        for positive in [True]*4 + [False]*4:
            rows.append(_rec(i, regime, "POSITIV RAPPORTDRIFT" if positive else "NEGATIV RAPPORTDRIFT", "STARK VINSTKVALITET"))
            outs.append({"record_id": f"r{i}", "horizon": "1m", "return_pct": .1 if positive else -.02})
            i += 1
    dossier=pd.DataFrame([{"Hypotes":"Post-Report Drift","Regimrobusthet":"Ej verifierad","Signalöverlapp":"Ej verifierad","Blockerare":"regimrobusthet, signalöverlapp, kostnad/omsättning","Nästa beslut":"Test."}])
    out=apply_dossier_robustness(dossier,pd.DataFrame(rows),pd.DataFrame(outs)).iloc[0]
    assert "regimrobusthet" not in out["Blockerare"]
    assert out["Regimrobusthet"] == "Stöd i flera regimer"
    assert "kostnad/omsättning" in out["Blockerare"]


def test_app_wires_robustness_and_release_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "apply_dossier_robustness(build_review_dossiers(research_queue), recs, outs)" in app
