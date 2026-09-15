from value_trap_discriminator import assess_value_trap_vs_market_wrong

def test_good_business_with_positive_evidence_can_be_market_wrong():
    r=assess_value_trap_vs_market_wrong({
      "Värdering":85,"Kvalitet":85,"Risk":80,"FCF-yield":.07,"Omsättningstillväxt":.08,
      "Vinsttillväxt":.12,"Vinstmarginal":.15,"Revision breadth nivå":2,"KPI Inflection nivå":2,
      "Management execution nivå":2,"Analysis Confidence Score":80,"Bolagsbedömning nivå":"green"})
    assert r["Value Trap verdict"]=="MARKET_WRONG"
    assert r["Value Trap nivå"]==3

def test_cheap_low_quality_high_debt_can_be_value_trap():
    r=assess_value_trap_vs_market_wrong({
      "Värdering":95,"Kvalitet":30,"Risk":25,"FCF-yield":-.03,"Omsättningstillväxt":-.15,
      "Vinsttillväxt":-.30,"Vinstmarginal":-.10,"Skuld/eget kapital":350,"Bolagsbedömning nivå":"red"})
    assert r["Value Trap verdict"]=="VALUE_TRAP"
    assert r["Value Trap nivå"]<0

def test_analyst_or_cheapness_alone_is_not_market_wrong():
    r=assess_value_trap_vs_market_wrong({"Värdering":90,"Kvalitet":50,"Risk":50})
    assert r["Value Trap verdict"]!="MARKET_WRONG"

def test_low_analysis_confidence_caps_bullish_value_call():
    r=assess_value_trap_vs_market_wrong({
      "Värdering":90,"Kvalitet":90,"Risk":85,"FCF-yield":.08,"Omsättningstillväxt":.10,
      "Vinsttillväxt":.10,"Vinstmarginal":.20,"Revision breadth nivå":2,"KPI Inflection nivå":2,
      "Analysis Confidence Score":30})
    assert r["Value Trap nivå"]<=1
    assert "svag data" in r["Value Trap Test"].lower()

def test_advisory_only():
    src=open('value_trap_discriminator.py',encoding='utf-8').read()
    assert 'påverkar ännu inte Borsifys ranking' in src

def test_app_wires_value_trap_layer():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.37.0"' in app
    assert 'add_value_trap_test(ranked)' in app
    assert '"Value Trap-test"' in app
