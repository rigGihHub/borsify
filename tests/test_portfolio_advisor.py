from portfolio_advisor import assess_holding

def test_hold_when_no_clear_sell_signal():
    r=assess_holding(100,{"Pris":110,"Borsify Score":72,"Kvalitet":75,"Risk":70,"3 mån":.08,"Avstånd SMA200":.05})
    assert r["Status"]=="BEHÅLL"
    assert abs(r["Utveckling"]-.10)<1e-12

def test_reconsider_when_multiple_model_weaknesses():
    r=assess_holding(100,{"Pris":80,"Borsify Score":38,"Kvalitet":35,"Risk":30,"3 mån":-.25,"Avstånd SMA200":-.15})
    assert r["Status"]=="OMPRÖVA"
    assert "säljsignal" in r["Borsify råd"].lower()

def test_watch_on_one_material_weakness():
    r=assess_holding(100,{"Pris":98,"Borsify Score":44,"Kvalitet":70,"Risk":70,"3 mån":.02,"Avstånd SMA200":.01})
    assert r["Status"]=="BEVAKA"

def test_large_gain_with_weakening_support_flags_profit_risk():
    r=assess_holding(100,{"Pris":140,"Borsify Score":55,"Kvalitet":70,"Risk":70,"3 mån":.05,"Avstånd SMA200":.03})
    assert r["Status"]=="VINSTSÄKRA?"
