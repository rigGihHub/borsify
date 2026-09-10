import pandas as pd
from missed_winner_patterns import classify_frozen_patterns, build_miss_pattern_table, miss_pattern_summary


def test_classification_uses_frozen_fields_only():
    tags = classify_frozen_patterns({"quality": 80, "valuation": 35, "setup": 60, "risk": 70, "coverage": .9})
    assert "Dyra kvalitetsbolag" in tags
    assert "Hög kvalitet" in tags


def test_overrepresentation_identifies_recurring_pattern():
    snaps=[]; outs=[]
    for i in range(20):
        sid=f"s{i}"
        expensive_quality = i < 4
        snaps.append({"snapshot_id":sid,"quality":80 if expensive_quality else 60,"valuation":35 if expensive_quality else 60,"setup":60,"risk":70,"coverage":.9})
        # all four expensive-quality names are misses; plus one unrelated miss
        miss = i < 4 or i == 10
        outs.append({"snapshot_id":sid,"horizon":"1m","missed_winner":int(miss),"return_pct":.22 if miss else .01})
    table=build_miss_pattern_table(pd.DataFrame(outs), pd.DataFrame(snaps), "1m", min_misses=3)
    row=table[table.pattern.eq("Dyra kvalitetsbolag")].iloc[0]
    assert row.misses == 4
    assert row.overrepresentation > 1.25
    assert row.status == "Återkommande missmönster"


def test_pattern_not_called_systematic_on_tiny_sample():
    snaps=pd.DataFrame([{"snapshot_id":"a","quality":80,"valuation":35,"setup":60,"risk":70,"coverage":.9}])
    outs=pd.DataFrame([{"snapshot_id":"a","horizon":"1m","missed_winner":1,"return_pct":.2}])
    table=build_miss_pattern_table(outs, snaps, min_misses=3)
    assert not (table.status == "Återkommande missmönster").any()


def test_missing_frozen_fields_are_not_backfilled():
    snaps=pd.DataFrame([{"snapshot_id":"a"},{"snapshot_id":"b"},{"snapshot_id":"c"}])
    outs=pd.DataFrame([{"snapshot_id":x,"horizon":"1m","missed_winner":1,"return_pct":.2} for x in "abc"])
    table=build_miss_pattern_table(outs, snaps, min_misses=3)
    assert set(table.pattern) == {"Ingen tydlig fryst faktor"}


def test_summary_is_diagnostic_only():
    table=pd.DataFrame([{"pattern":"Hög kvalitet","misses":3,"miss_share":.6,"cohort_share":.3,"overrepresentation":2.0,"median_return":.2,"status":"Återkommande missmönster"}])
    s=miss_pattern_summary(table)
    assert s["status"] == "Mönster hittat"
    assert "inte en automatisk modelländring" in s["text"]
