import pandas as pd
from universe_quality import assess_universe_quality, apply_universe_quality, filter_rankable_universe, quality_summary

def good_row():
    hist=pd.DataFrame({"Close":[100+i*.1 for i in range(150)]})
    return {
        "Ticker":"TEST","Namn":"Test AB","Pris":115.0,"Prisdatum":"2026-09-02",
        "Valuta":"SEK","_history":hist,"P/E":15,"Forward P/E":14,
        "ROE":.18,"Vinstmarginal":.12,"Börsvärde BSEK":10,
    }

def test_good_market_data_is_verified():
    q=assess_universe_quality(good_row())
    assert q["Universe QC"]=="VERIFIERAD"
    assert q["Universe QC Score"]>=80

def test_missing_price_is_hard_exclusion():
    r=good_row(); r["Pris"]=None
    q=assess_universe_quality(r)
    assert q["Universe QC"]=="EXKLUDERA"

def test_short_history_is_hard_exclusion():
    r=good_row(); r["_history"]=pd.DataFrame({"Close":[1,2,3]})
    q=assess_universe_quality(r)
    assert q["Universe QC"]=="EXKLUDERA"

def test_missing_fundamentals_can_be_partial_not_invented():
    r=good_row()
    for k in ["P/E","Forward P/E","ROE","Vinstmarginal","Börsvärde BSEK"]:
        r[k]=None
    q=assess_universe_quality(r)
    assert q["Universe QC"]=="DELVIS VERIFIERAD"
    assert "saknar centrala fundamentala datapunkter" in q["Universe QC Problem"]

def test_filter_removes_only_hard_exclusions():
    good=good_row()
    bad=good_row(); bad["Ticker"]="BAD"; bad["Pris"]=None
    df=apply_universe_quality(pd.DataFrame([good,bad]))
    rankable,rejected=filter_rankable_universe(df)
    assert list(rankable["Ticker"])==["TEST"]
    assert list(rejected["Ticker"])==["BAD"]

def test_quality_summary_counts_statuses():
    good=good_row()
    partial=good_row(); partial["Ticker"]="PART"
    for k in ["P/E","Forward P/E","ROE","Vinstmarginal","Börsvärde BSEK"]:
        partial[k]=None
    df=apply_universe_quality(pd.DataFrame([good,partial]))
    s=quality_summary(df)
    assert s["verified"]==1
    assert s["partial"]==1
