from exceptional_deal_nose import assess_exceptional_deal

def test_exceptional_requires_multiple_pillars_and_good_entry():
    r=assess_exceptional_deal({"Värdering":90,"Kvalitet":88,"Risk":85,"FCF-yield":.07,"Riktkurs potential":.30,
      "Ingångsläge nivå":"green","Bolagsbedömning nivå":"green","Mispriced acceleration nivå":2,"Revision breadth nivå":2,
      "Deal Conviction Score":80,"Analysis Confidence Score":80},"year")
    assert r["Deal Nose nivå"]==3

def test_hot_stock_gets_chase_penalty():
    base={"Värdering":85,"Kvalitet":85,"Risk":80,"Ingångsläge nivå":"orange","Bolagsbedömning nivå":"green",
          "Mispriced acceleration nivå":2,"Hidden inflection nivå":2,"1 mån":.35,"3 mån":.65,"RSI14":84,"Avstånd SMA200":.30}
    r=assess_exceptional_deal(base,"year")
    assert r["Deal Nose nivå"]<3
    assert "chase-avdrag" in r["Deal Nose förklaring"]

def test_cheap_junk_is_not_exceptional():
    r=assess_exceptional_deal({"Värdering":95,"Kvalitet":25,"Risk":20,"Ingångsläge nivå":"green","Bolagsbedömning nivå":"red"},"year")
    assert r["Deal Nose nivå"]<2

def test_target_upside_alone_cannot_create_signal():
    r=assess_exceptional_deal({"Riktkurs potential":1.0,"Ingångsläge nivå":"green"},"year")
    assert r["Deal Nose nivå"]==0

def test_deal_nose_is_advisory_not_ranking_input():
    src=open('exceptional_deal_nose.py',encoding='utf-8').read()
    assert 'påverkar ännu inte Borsify-rankingen' in src

def test_app_exposes_deal_nose():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.39.0"' in app
    assert 'add_exceptional_deal_nose(ranked, horizon)' in app
    assert '"Deal Nose"' in app
