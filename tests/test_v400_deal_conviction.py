from deal_conviction import assess_deal_conviction

def test_correlated_operating_signals_are_capped_as_one_family():
    r=assess_deal_conviction({"Mispriced acceleration nivå":3,"Margin recovery nivå":3,"Cash conversion inflection nivå":3,"Operating leverage nivå":3},"long")
    assert r["Deal Conviction oberoende familjer"] == 1
    assert r["Deal Conviction nivå"] <= 1

def test_cross_family_confluence_gets_high_conviction():
    r=assess_deal_conviction({"Mispriced acceleration nivå":3,"Revision breadth nivå":2,"Affärsläge nivå":3,"Ignored compounder nivå":2,"Ingångsläge nivå":"green","Bolagsbedömning nivå":"green"},"long")
    assert r["Deal Conviction oberoende familjer"] == 4
    assert r["Deal Conviction nivå"] == 3
    assert r["Deal Conviction Score"] >= 72

def test_negative_families_reduce_conviction():
    r=assess_deal_conviction({"Mispriced acceleration nivå":-1,"Revision breadth nivå":-1,"Affärsläge nivå":2,"Ingångsläge nivå":"green","Bolagsbedömning nivå":"green"},"long")
    assert r["Deal Conviction nivå"] == -1

def test_short_horizon_ignores_long_duration_optionality_family():
    r=assess_deal_conviction({"Ignored compounder nivå":3,"Balance-sheet optionality nivå":3},"medium")
    assert r["Deal Conviction oberoende familjer"] == 0

def test_app_and_ranking_use_conviction_instead_of_signal_stack():
    app=open("app.py",encoding="utf-8").read(); rank=open("horizon_rankings.py",encoding="utf-8").read(); ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.38.0"' in app
    assert "add_deal_conviction(ranked, horizon)" in app
    assert '"Deal Conviction Score"' in rank
    assert '[col,"Revision breadth rangvärde"' not in rank
    assert '"Deal Conviction förklaring"' in ledger
