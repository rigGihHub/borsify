from hidden_inflection import assess_hidden_inflection

def test_hidden_inflection_needs_multiple_early_signals():
    r=assess_hidden_inflection({"Fresh Change New Positives":1,"Fresh Change New Negatives":0,"Fresh Change Positive Count":1,"Fresh Change Negative Count":0,"Report Delta positiva":1,"Report Delta negativa":0,"1 mån":.03,"3 mån":.05,"Avstånd SMA200":.04,"Kvalitet":70})
    assert r["Hidden inflection nivå"] >= 2

def test_hidden_inflection_downgrades_if_price_already_ran():
    r=assess_hidden_inflection({"Fresh Change New Positives":1,"Fresh Change New Negatives":0,"Fresh Change Positive Count":1,"Fresh Change Negative Count":0,"Report Delta positiva":1,"Report Delta negativa":0,"1 mån":.20,"3 mån":.30,"Kvalitet":70})
    assert r["Hidden inflection nivå"] == 1

def test_negative_signals_block_hidden_inflection():
    r=assess_hidden_inflection({"Fresh Change New Positives":1,"Fresh Change Positive Count":1,"Fresh Change Negative Count":2,"Report Delta negativa":2,"Kvalitet":70})
    assert r["Hidden inflection nivå"] == -1

def test_app_and_ranking_wired():
    app=open("app.py",encoding="utf-8").read(); rank=open("horizon_rankings.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "Hidden inflection" in app
    assert "add_hidden_inflection(ranked)" in app
    assert "add_hidden_inflection(out)" in rank
    assert '"Deal Conviction Score"' in rank
