import pandas as pd
from catalyst_engine import build_catalyst_assessment, classify_news_catalyst

NOW = pd.Timestamp('2026-09-01T05:00:00Z')

def test_positive_inflection_becomes_catalyst():
    case = {
        'Inflection Signal': 'Positiv inflektion', 'Inflection Confidence': 75,
        'EPS-estimat förändring': .08, 'Omsättning acceleration': .04,
    }
    r = build_catalyst_assessment(case, {}, NOW)
    assert r['Catalyst Signal'] == 'Tydlig möjlig katalysator'
    assert r['Catalyst Support'] is False
    assert r['Primary Catalyst'] == 'Fundamental inflektion'

def test_report_is_control_point_not_positive_support():
    r = build_catalyst_assessment({}, {'earnings': '2026-09-15', 'news': []}, NOW)
    assert r['Catalyst Signal'] == 'Närliggande kontrollpunkt'
    assert r['Catalyst Support'] is False
    assert r['Primary Catalyst'] == 'Kommande rapport'

def test_profit_warning_vetoes_positive_headline():
    case = {'Inflection Signal':'Positiv inflektion','Inflection Confidence':80,'EPS-estimat förändring':.06}
    events = {'news':[{'title':'Company issues profit warning and cuts guidance'}]}
    r = build_catalyst_assessment(case, events, NOW)
    assert r['Catalyst Signal'] == 'Ny risk måste verifieras först'
    assert r['Catalyst Support'] is False
    assert 'vinst' in r['Catalyst Warnings'].lower() or 'sänkt' in r['Catalyst Warnings'].lower()

def test_undated_positive_headline_is_not_current_catalyst():
    r = build_catalyst_assessment({}, {'news':[{'title':'Bolaget vinner kontrakt värt 500 MSEK'}]}, NOW)
    assert r['Catalyst Signal'] == 'Ingen tydlig katalysator verifierad'
    assert 'utan verifierbart datum' in r['Catalyst Warnings']

def test_deleveraging_can_be_catalyst():
    r = build_catalyst_assessment({'Skuldförändring': -.25}, {}, NOW)
    assert r['Catalyst Support'] is False
    assert r['Primary Catalyst'] == 'Skuldminskning'

def test_no_evidence_means_no_catalyst():
    r = build_catalyst_assessment({}, {}, NOW)
    assert r['Catalyst Signal'] == 'Ingen tydlig katalysator verifierad'
    assert r['Catalyst Support'] is False

def test_uncertain_acquisition_not_positive_by_default():
    label, direction, strength = classify_news_catalyst('Company announces acquisition of rival')
    assert direction == 'uncertain'
    assert strength > 0

def test_guidance_cut_is_negative():
    label, direction, strength = classify_news_catalyst('Company cuts guidance after weak demand')
    assert direction == 'negative'
    assert strength == 3
