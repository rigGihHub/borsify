import json
import pandas as pd

from discovery_champion_challenger import (
    REGISTERED_VERSION, default_discovery_challengers, registry_table,
    discovery_selection_flags, prospective_discovery_results, discovery_challenger_summary,
)


def _universe(n=30):
    rows=[]
    for i in range(n):
        rows.append({"Ticker":f"S{i:02d}","Namn":f"Stock {i}","Pris":100,"Borsify Score":80-i,
                     "Mellan Score":70-i/3,"Års Score":68-i/4,"Livstid Score":66-i/5,
                     "Kvalitet":60+i/2,"Värdering":55,"Marknadsläge":60,"Risk":70,"Datatäckning":.9,
                     "REVERSAL Score":50})
    rows[-1].update({"Kvalitet":90,"Värdering":30,"Års Score":72,"Borsify Score":45})
    return pd.DataFrame(rows)


def test_registry_is_locked_to_v350_and_fingerprinted():
    reg=registry_table()
    assert REGISTERED_VERSION == "3.50.0"
    assert len(reg) >= 7
    assert reg["Definition"].str.len().eq(16).all()
    assert reg["Förregistrerad version"].eq("3.50.0").all()


def test_challenger_keeps_same_pool_size_and_can_swap_in_target():
    u=_universe()
    flags=discovery_selection_flags(u, max_candidates=24)
    assert flags["discovery_champion_selected"].sum() == 24
    spec=[s for s in default_discovery_challengers() if s.challenger_id=="expensive_quality_v1"][0]
    assert flags[spec.challenger_id].sum() == 24
    assert flags.loc[u.index[-1], spec.challenger_id] == 1


def test_old_or_missing_frozen_flags_are_never_backfilled():
    snaps=pd.DataFrame([{"snapshot_id":"old","captured_date":"2026-09-07","model_version":"3.49.0","discovery_champion_selected":1,"discovery_challenger_flags":json.dumps({"quality_plus_one_v1":1})}])
    outs=pd.DataFrame([{"snapshot_id":"old","horizon":"1m","return_pct":.2,"return_percentile":.95}])
    assert prospective_discovery_results(snaps, outs).empty


def test_prospective_result_requires_independent_mature_evidence():
    snaps=[]; outs=[]
    for d in ["2026-09-08","2026-09-09","2026-09-10"]:
        for i in range(20):
            sid=f"{d}-{i}"
            flags={s.challenger_id: int(i<10) for s in default_discovery_challengers()}
            snaps.append({"snapshot_id":sid,"captured_date":d,"model_version":"3.50.0","discovery_champion_selected":int(i<10),"discovery_challenger_flags":json.dumps(flags)})
            outs.append({"snapshot_id":sid,"horizon":"1m","return_pct":.2 if i<2 else 0,"return_percentile":.95 if i<2 else .5})
    res=prospective_discovery_results(pd.DataFrame(snaps),pd.DataFrame(outs))
    assert not res.empty
    assert res["Status"].eq("För lite underlag").all()
    assert "väntar" in discovery_challenger_summary(pd.DataFrame())["text"].lower()


def test_no_score_or_production_column_is_created():
    flags=discovery_selection_flags(_universe(), max_candidates=24)
    assert not any("score" in c.lower() for c in flags.columns)
    assert set(flags["discovery_champion_selected"].unique()) <= {0,1}
