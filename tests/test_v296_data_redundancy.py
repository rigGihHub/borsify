import pandas as pd
from fundamental_redundancy import assess_fundamental_redundancy
from case_quality_gate import build_case_quality_gate

def _frame(rows):
    return pd.DataFrame(rows, index=[pd.Timestamp("2025-12-31")]).T

def test_internal_paths_agree_but_are_not_called_external_sources():
    snap={"Pris":100,"_Raw marketCap":1e9,"_Raw freeCashflow":1e8,"_Raw totalDebt":2e8,"_Raw totalRevenue":2e9,"_Raw netIncome":1.2e8}
    raw={"fast_info":{"last_price":101,"market_cap":1.02e9},"cashflow":_frame({"Free Cash Flow":9.5e7}),"balance":_frame({"Total Debt":2.1e8}),"income":_frame({"Total Revenue":1.9e9,"Net Income":1.15e8}),"external_verification_status":"SAKNAS"}
    out=assess_fundamental_redundancy(snap,raw)
    assert out["Redundans status"]=="INTERN KONTROLL OK"
    assert out["Redundans kontroller"]>=4
    assert out["Extern verifiering"]=="SAKNAS"
    assert "inte oberoende datakällor" in out["Redundans metod"]

def test_extreme_market_cap_contradiction_stops_case():
    out=assess_fundamental_redundancy({"Pris":100,"_Raw marketCap":1e9},{"fast_info":{"last_price":100,"market_cap":1e8}})
    assert out["Redundans status"]=="STOPP – MOTSÄGELSE"
    assert "börsvärdet" in out["Redundans stopp"]

def test_redundancy_stop_is_hard_veto_in_case_gate():
    case={"Djupkontroll":"Klarar djupkontroll","Value Trap Risk":10,"Deep Confidence":80,"Inflection Confidence":70,"Inflection Signal":"Positiv inflektion","Förväntningsriktning":"positiv","Mispricing Signal":"Tydlig möjlig felprissättning","Scenario Status":"OK","Scenario Verdict":"Attraktiv asymmetri","Scenario Asymmetry":2.5,"Scenario Confidence":75,"Catalyst Signal":"Tydlig möjlig katalysator","Catalyst Support":True,"Catalyst Confidence":70,"Fundamental Data status":"STARKT UNDERLAG","Redundans status":"STOPP – MOTSÄGELSE","Redundans stopp":"börsvärdet skiljer 90%"}
    out=build_case_quality_gate(case)
    assert out["Case Gate"]=="Ej toppcase"
    assert "motsäger varandra" in out["Case Vetoes"]

def test_missing_secondary_paths_never_become_fake_confirmation():
    out=assess_fundamental_redundancy({"Pris":100},{"fast_info":{}})
    assert out["Redundans status"]=="FÖR LITE UNDERLAG"
    assert out["Redundans kontroller"]==0
