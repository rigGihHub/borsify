from market_blind_spot import assess_market_blind_spot

def test_low_coverage_never_qualifies_without_observed_analyst_count():
    r=assess_market_blind_spot({"Early Mispricing status":"EARLY_MISPRICING","Early Mispricing Score":80,"Underfollowed Quality nivå":3,"Analysis Confidence Score":80})
    assert r["Market Blind Spot nivå"]<3
    assert "saknas" in r["Market Blind Spot counter"]

def test_two_independent_reasons_can_create_credible_blind_spot():
    r=assess_market_blind_spot({"Early Mispricing status":"EARLY_MISPRICING","Early Mispricing Score":85,"Analytiker antal":2,"Underfollowed Quality nivå":2,"Earnings power noise nivå":2,"Analysis Confidence Score":80,"1 mån":.04,"Relativ marknad 3 mån":.03})
    assert r["Market Blind Spot status"]=="CREDIBLE_BLIND_SPOT"
    assert r["Market Blind Spot families"]>=2

def test_price_already_noticing_case_blocks_top_tier():
    r=assess_market_blind_spot({"Early Mispricing status":"EARLY_MISPRICING","Early Mispricing Score":90,"Analytiker antal":1,"Underfollowed Quality nivå":3,"Hidden inflection nivå":3,"Analysis Confidence Score":90,"1 mån":.25})
    assert r["Market Blind Spot status"]=="BLIND_SPOT_CLOSING"

def test_no_early_mispricing_means_no_blind_spot_claim():
    r=assess_market_blind_spot({"Early Mispricing status":"NO_EARLY_WINDOW","Analytiker antal":1,"Underfollowed Quality nivå":3,"Earnings power noise nivå":3})
    assert r["Market Blind Spot status"]=="NO_MISPRICING_BASE"

def test_low_confidence_degrades_positive_blind_spot():
    r=assess_market_blind_spot({"Early Mispricing status":"EARLY_MISPRICING","Early Mispricing Score":85,"Analytiker antal":2,"Underfollowed Quality nivå":2,"Earnings power noise nivå":2,"Analysis Confidence Score":30})
    assert r["Market Blind Spot status"]=="BLIND_SPOT_LOW_CONFIDENCE"

def test_app_integrates_and_does_not_rank_by_blind_spot():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert 'add_market_blind_spot(ranked)' in app
    assert '"Early Mispricing", "Market Blind Spot", "Catalyst-to-Recognition"' in app
    assert '"Recognition Window payoff", "Market-Implied Expectations", "Deal Conviction", "Analysis Confidence"' in app
    # No sort/rank key is allowed to use this advisory field.
    assert 'sort_values("Market Blind Spot' not in app
