import json
import pandas as pd

from research_cost_turnover import cost_turnover_robustness, apply_cost_turnover
from research_dossier_robustness import CHECK_PENDING


def _snap(post=True, turnover=25.0):
    return json.dumps({
        "Post-report status": "POSITIV RAPPORTDRIFT" if post else "NEGATIV RAPPORTDRIFT",
        "Omsättning MSEK/dag": turnover,
    })


def _dataset(ret_good=.08, ret_bad=-.01, symbols=12, months=8):
    recs=[]; outs=[]; i=0
    # Spread ledger observations over >90 days so observed churn can be measured.
    for m in range(months):
        date=(pd.Timestamp('2026-01-01') + pd.Timedelta(days=m*30)).strftime('%Y-%m-%d')
        for s in range(symbols):
            good=(m % 2 == 0)
            rid=f'r{i}'
            recs.append({"record_id":rid,"symbol":f'S{s}',"captured_date":date,"horizon_type":"long","snapshot_json":_snap(good,30+s)})
            outs.append({"record_id":rid,"horizon":"1m","return_pct":ret_good if good else ret_bad})
            i += 1
    # Add enough positive matured outcomes for the cost test.
    while sum('POSITIV RAPPORTDRIFT' in r['snapshot_json'] for r in recs) < 12:
        rid=f'r{i}'; s=i%symbols
        recs.append({"record_id":rid,"symbol":f'S{s}',"captured_date":"2026-09-01","horizon_type":"long","snapshot_json":_snap(True,35)})
        outs.append({"record_id":rid,"horizon":"1m","return_pct":ret_good}); i+=1
    return pd.DataFrame(recs), pd.DataFrame(outs)


def test_cost_turnover_requires_mature_outcomes():
    recs=pd.DataFrame([{"record_id":"r1","symbol":"A","captured_date":"2026-01-01","horizon_type":"long","snapshot_json":_snap(True)}])
    outs=pd.DataFrame([{"record_id":"r1","horizon":"1m","return_pct":.1}])
    assert cost_turnover_robustness("Post-Report Drift", recs, outs)["status"] == CHECK_PENDING


def test_cost_turnover_can_verify_robust_positive_signal():
    recs,outs=_dataset(.08,-.01)
    result=cost_turnover_robustness("Post-Report Drift",recs,outs)
    assert result["cost_status"] == "Robust mot kostnadsstress"
    assert result["status"] == "Kostnad/omsättning verifierad"
    assert result["liquidity_coverage"] >= .60
    assert result["stress_net_median"] > 0


def test_cost_turnover_flags_cost_sensitive_signal():
    recs,outs=_dataset(.002,-.01)
    result=cost_turnover_robustness("Post-Report Drift",recs,outs)
    assert result["cost_status"] == "Kostnadskänslig"
    assert result["status"] == "Kostnad/omsättning ifrågasatt"


def test_partial_verification_keeps_blocker_when_liquidity_missing():
    recs,outs=_dataset(.08,-.01)
    recs["snapshot_json"] = recs["snapshot_json"].map(lambda raw: json.dumps({k:v for k,v in json.loads(raw).items() if k != "Omsättning MSEK/dag"}))
    dossier=pd.DataFrame([{"Hypotes":"Post-Report Drift","Kostnad/omsättning":"Ej verifierad","Blockerare":"kostnad/omsättning, datakvalitet","Nästa beslut":"Test."}])
    out=apply_cost_turnover(dossier,recs,outs).iloc[0]
    assert out["Kostnad/omsättning"] == "Delvis verifierad"
    assert "kostnad/omsättning" in out["Blockerare"]


def test_app_wires_cost_turnover_and_release_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "apply_cost_turnover(apply_incremental_value(apply_dossier_robustness(build_review_dossiers(research_queue), recs, outs), recs, outs), recs, outs)" in app
    assert "kostnads-/omsättningsrobusthet" in app
