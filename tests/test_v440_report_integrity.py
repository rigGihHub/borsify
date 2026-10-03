import pandas as pd
import pytest

from report_sources import candidate_report, accept_report_candidate
from report_verification import verify_report_text, can_support_fresh_recommendation
from report_delta_engine import build_report_delta
from report_delta_memory import snapshot_from_report_delta
from report_fetcher import original_publication_time, verify_primary_report_from_events
from buy_card import build_buy_card
from market_implied_expectations import assess_market_implied_expectations

URL = 'https://view.news.eu.nasdaq.com/view?id=report'


def candidate(name='Company A'):
    return {**candidate_report(name + ' Q2 2026 report', '2026-07-15T08:00Z', URL), 'issuer_name': name}


def body(name='Company A'):
    return name + ' Q2 2026 interim report. Revenue SEK 100 million. Cash flow SEK 20 million. ' + ('The company describes its operations and risks. ' * 40)


def test_wrong_company_and_unknown_identity_never_mark_read():
    assert verify_report_text(candidate(), 'Sverige', body('Company B'), company_name='Company A')['Rapport läst'] is False
    c = candidate(); c.pop('issuer_name')
    assert verify_report_text(c, 'Sverige', body())['Rapport läst'] is False


def test_publication_metadata_is_not_independently_verified_until_matched():
    c = candidate()
    result = verify_report_text(c, 'Sverige', body())
    assert result['Rapport läst'] is True and result['Rapport bolag verifierat'] is True
    assert result['Rapport datum tolkat'] is True and result['Rapport datum verifierat'] is False
    c['original_published_at'] = c['published_at']
    assert verify_report_text(c, 'Sverige', body())['Rapport datum verifierat'] is True
    c['original_published_at'] = '2026-06-01T08:00Z'
    assert verify_report_text(c, 'Sverige', body())['Rapport datum verifierat'] is False


@pytest.mark.parametrize('title', ['Årsredovisning 2025', 'Bokslutskommuniké 2025', 'Bokslutsrapport 2025'])
def test_swedish_report_titles_recognized(title):
    assert candidate_report(title, '', URL)['is_financial_report'] is True


def test_only_independently_mapped_issuer_domain_is_accepted():
    c = {**candidate_report('Investor Q2 2026 report', '', 'https://www.investorab.com/report'), 'issuer_name': 'Investor AB ser. B'}
    assert accept_report_candidate(c, 'Sverige')[0] is True
    c['issuer_name'] = 'Another Company'
    assert accept_report_candidate(c, 'Sverige')[0] is False


def test_facts_are_cited_separately_from_numeric_interpretation():
    result = verify_report_text(candidate(), 'Sverige', body())
    assert all(f['källa'] == URL and f['rapportperiod'] == 'Q2 2026' for f in result['Rapport faktacitat'])
    assert 'ej avstämda' in result['Rapport fakta status']


def test_guidance_needs_event_time_and_company_identity():
    metrics = {'Rapport bolagsnamn':'Company A', 'Rapportmått periodslut':'2026-06-30', 'Senaste EPS-överraskning':.1,
               'Omsättning acceleration':.1,'Marginal YoY förändring':.02,'Vinst YoY senaste kvartal':.2}
    post = {'Post-report datum':'2026-07-15','Post-report dagar sedan':8,'Post-report reaktion':.01}
    for title, timestamp in [('Company A raises guidance','2020-01-01'),('Company B raises guidance','2026-07-15T08:00Z'),('Company A raises guidance','')]:
        result = build_report_delta(metrics, post, {'news':[{'title':title,'published_at':timestamp}]})
        assert 'höjt guidningen' not in result['Report Delta styrkor']
    result = build_report_delta(metrics, post, {'news':[{'title':'Company A raises guidance','published_at':'2026-07-15T08:00Z'}]})
    assert 'bolaget har höjt guidningen' in result['Report Delta styrkor']


def test_pre_report_revision_window_not_claimed_as_post_report_support():
    metrics = {'Rapportmått periodslut':'2026-06-30','EPS-estimat förändring':.1,'EPS-estimat jämförelseperiod':'30 dagar','Estimat tillförlitlighetsvikt':.8}
    result = build_report_delta(metrics, {'Post-report datum':'2026-07-15','Post-report dagar sedan':8})
    assert not any('efter rapporten' in x for x in result['Report Delta styrkor'])


def test_period_conflict_and_unknown_reaction_block_discovery():
    m={'Rapportmått periodslut':'2026-06-30','Senaste EPS-överraskning':.1,'Omsättning acceleration':.1,'Marginal YoY förändring':.02,'Vinst YoY senaste kvartal':.2}
    p={'Post-report datum':'2026-07-15','Post-report dagar sedan':8}
    assert build_report_delta(m,p)['Report Delta kandidat'] is False
    m['Rapportmått periodkonflikt'] = True; p['Post-report reaktion'] = .01
    result = build_report_delta(m,p)
    assert result['Report Delta kandidat'] is False
    assert snapshot_from_report_delta('TEST',m,p,result,'2026-07-23') is None


def test_original_metadata_extraction():
    html = '<script type="application/ld+json">{"datePublished":"2026-07-15T08:00Z"}</script>'
    assert original_publication_time(html) == '2026-07-15T08:00Z'


def test_failed_report_does_not_hide_a_later_valid_report(monkeypatch):
    events = {'news':[{'title':'Company A Q2 2026 report','link':URL+'1','published_at':'2026-07-15T08:00Z'},
                      {'title':'Company A Q2 2026 report','link':URL+'2','published_at':'2026-07-14T08:00Z'}]}
    calls=[]
    def fetch(url,**kwargs):
        calls.append(url)
        return {'ok':True,'text':'Cookie page' if len(calls)==1 else body(),'resolved_url':url}
    monkeypatch.setattr('report_fetcher.fetch_report_text',fetch)
    report=verify_primary_report_from_events(events,'Sverige',company_name='Company A')
    assert report['Rapport läst'] is True and len(calls)==2


def test_investment_company_explanations_use_specialist_basis():
    row={'Investmentbolag':True,'Investmentbolag status':'Delvis look-through','Investmentbolag enkel förklaring':'Substans och innehav är delvis täckta.',
         'Kvalitet':96,'ROE':.3,'Vinstmarginal':.9,'FCF-yield':.177}
    card=build_buy_card(row,'lifetime')
    assert 'Substans' in card['Därför kan aktien vara värd att köpa']
    assert 'försäljningen' not in card['Därför kan aktien vara värd att köpa']
    assert '17.7' not in assess_market_implied_expectations(row)['Market-Implied Expectations förklaring']
