from revision_breadth import assess_revision_breadth

def test_strong_revision_breadth_emergence():
    r=assess_revision_breadth({
        "Analytiker antal":10,"Reviderande analytiker senaste period":6,
        "EPS-revisionsbalans":.30,"EPS-estimat förändring":.02,
        "Konsensus bullish andel":.60,"1 mån":.05,"Avstånd SMA200":.07
    })
    assert r["Revision breadth nivå"] == 3
    assert abs(r["Revision breadth andel"]-.6)<1e-9

def test_missing_analyst_count_is_not_opportunity():
    r=assess_revision_breadth({"Reviderande analytiker senaste period":3,"EPS-revisionsbalans":.3})
    assert r["Revision breadth nivå"] == 0

def test_negative_revisions_block():
    r=assess_revision_breadth({
        "Analytiker antal":10,"Reviderande analytiker senaste period":5,
        "EPS-revisionsbalans":-.30,"EPS-estimat förändring":-.04
    })
    assert r["Revision breadth nivå"] == -1

def test_crowded_or_price_run_downgrades():
    r=assess_revision_breadth({
        "Analytiker antal":10,"Reviderande analytiker senaste period":6,
        "EPS-revisionsbalans":.35,"EPS-estimat förändring":.03,
        "Konsensus bullish andel":.85,"1 mån":.25,"Avstånd SMA200":.22
    })
    assert r["Revision breadth nivå"] == 1

def test_app_and_ranking_wired():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "add_revision_breadth(ranked)" in app
    assert "add_revision_breadth(out)" in rank
    assert '"Deal Conviction Score"' in rank
    assert '"Revision breadth förklaring"' in ledger
