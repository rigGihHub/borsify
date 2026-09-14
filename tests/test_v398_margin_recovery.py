from margin_recovery_before_consensus import assess_margin_recovery_before_consensus

def test_strong_margin_recovery_before_consensus():
    r=assess_margin_recovery_before_consensus({
        "Marginal YoY förändring":.025,"Marginal YoY föregående kvartal":-.005,
        "Vinst YoY senaste kvartal":.12,"Vinst YoY föregående kvartal":.06,
        "Omsättning acceleration":.03,"EPS-estimat förändring":.01,"EPS-revisionsbalans":.20,
        "Konsensus bullish andel":.55,"Analytiker antal":8,"Kvalitet":75,"Värdering":70,
        "1 mån":.04,"3 mån":.08,"Avstånd SMA200":.06,"Ingångsläge nivå":"green"
    })
    assert r["Margin recovery nivå"] == 3

def test_no_recovery_without_margin_delta():
    r=assess_margin_recovery_before_consensus({
        "Marginal YoY förändring":.01,"Marginal YoY föregående kvartal":.005
    })
    assert r["Margin recovery nivå"] == 0

def test_recovery_downgraded_when_consensus_and_price_already_caught_up():
    r=assess_margin_recovery_before_consensus({
        "Marginal YoY förändring":.04,"Marginal YoY föregående kvartal":.01,
        "EPS-estimat förändring":.08,"EPS-revisionsbalans":.55,
        "Konsensus bullish andel":.82,"Analytiker antal":10,
        "1 mån":.25,"3 mån":.40,"Avstånd SMA200":.22,"Ingångsläge nivå":"red","Kvalitet":75
    })
    assert r["Margin recovery nivå"] == 1

def test_deteriorating_margin_blocks():
    r=assess_margin_recovery_before_consensus({
        "Marginal YoY förändring":-.08,"Marginal YoY föregående kvartal":-.02,"Kvalitet":70
    })
    assert r["Margin recovery nivå"] == -1

def test_app_and_ranking_wired():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.36.0"' in app
    assert "add_margin_recovery_before_consensus(ranked)" in app
    assert "add_margin_recovery_before_consensus(out)" in rank
    assert '"Deal Conviction Score"' in rank
    assert '"Margin recovery förklaring"' in ledger
