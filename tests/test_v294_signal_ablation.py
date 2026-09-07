import json
import numpy as np
import pandas as pd

from signal_ablation import (
    SHORT_WEIGHTS,
    MIN_ABLATION_CASES,
    prepare_short_ablation_data,
    short_signal_ablation,
    ablation_summary,
)
from recommendation_ledger import snapshot_columns


def _frames(n=36, harmful_catalyst=False):
    rows=[]
    outs=[]
    # Deterministic nonlinear ordering so ties/row order cannot manufacture the result.
    order=np.array([(i*17) % n for i in range(n)], dtype=float)
    centered=(order-order.mean())/(order.std() or 1)
    returns=centered*0.08
    for i in range(n):
        strength = 3 if harmful_catalyst else 18
        good=float(np.clip(50 + centered[i]*strength, 2, 98))
        snap={
            "Short Relative Strength": good,
            "Short Trend": float(np.clip(good + ((i % 5)-2)*2, 2, 98)),
            "Short Momentum": float(np.clip(good + ((i % 7)-3)*1.5, 2, 98)),
            "Short Participation": float(np.clip(good + ((i % 3)-1)*4, 2, 98)),
            "Short Revisions": float(np.clip(good + ((i % 4)-1.5)*3, 2, 98)),
            "Short Catalyst": float(np.clip(50-centered[i]*35 if harmful_catalyst else good + ((i % 6)-2.5)*2, 2, 98)),
            "Short Vetoes": "—",
        }
        rid=f"r{i}"
        rows.append({
            "record_id":rid,
            "symbol":f"S{i}",
            "captured_date":f"2024-{(i//28)+1:02d}-{(i%28)+1:02d}",
            "horizon_type":"short",
            "snapshot_json":json.dumps(snap),
        })
        outs.append({"record_id":rid,"horizon":"1m","return_pct":float(returns[i]),"excess_return_pct":float(returns[i])})
    return pd.DataFrame(rows),pd.DataFrame(outs)


def test_ablation_uses_exact_six_short_alpha_components_and_independent_cases():
    recs,outs=_frames()
    data=prepare_short_ablation_data(recs,outs,"1m")
    assert len(data)==36
    for _,(field,_) in SHORT_WEIGHTS.items():
        assert field in data.columns
    table=short_signal_ablation(recs,outs,"1m")
    assert set(table["Signal"])==set(SHORT_WEIGHTS)
    assert table["Oberoende case"].eq(36).all()
    assert table["Mätning"].eq("Mot index").all()


def test_ablation_can_flag_a_deliberately_harmful_component_for_review():
    recs,outs=_frames(harmful_catalyst=True)
    table=short_signal_ablation(recs,outs,"1m")
    catalyst=table[table["Signal"].eq("Katalysator")].iloc[0]
    assert catalyst["Förändring korrelation"] < 0
    assert catalyst["Förändring topp-botten"] <= 0
    assert catalyst["Status"] == "Bör granskas"
    summary=ablation_summary(table)
    assert summary["status"] == "Signal värd att granska"


def test_ablation_waits_for_enough_cases_instead_of_overreading_small_sample():
    recs,outs=_frames(n=MIN_ABLATION_CASES-1, harmful_catalyst=True)
    table=short_signal_ablation(recs,outs,"1m")
    assert not table.empty
    assert table["Status"].eq("För lite underlag").all()
    assert ablation_summary(table)["status"] == "För lite underlag"


def test_hard_veto_rows_are_excluded_from_additive_ablation():
    recs,outs=_frames(n=10)
    snap=json.loads(recs.loc[0,"snapshot_json"])
    snap["Short Vetoes"]="fallande lång trend"
    recs.loc[0,"snapshot_json"]=json.dumps(snap)
    data=prepare_short_ablation_data(recs,outs,"1m")
    assert len(data)==9
    assert "r0" not in set(data["record_id"])


def test_long_ledger_now_freezes_components_needed_for_future_exact_ablation():
    cols=snapshot_columns("long")
    assert "Growth Score" in cols
    assert "Marknadsläge" in cols


def test_v294_ui_exposes_ablation_without_auto_reweighting():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.26.0"' in app
    assert "Vilka kortsiktiga signaler gör faktiskt nytta?" in app
    assert "ändrar aldrig vikter automatiskt" in app
