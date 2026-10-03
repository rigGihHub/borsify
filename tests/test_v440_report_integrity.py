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


def test_repeated_view_reuses_report_evidence_but_changed_identity_rechecks(monkeypatch):
    import app
    calls = []
    def verify(events, country, company_name):
        calls.append((events, country, company_name))
        return {"Rapport läst": False, "issuer": company_name}
    monkeypatch.setattr(app, 'verify_primary_report_from_events', verify)
    cached = app.cached_primary_report_verification
    cached.clear()
    try:
        first = cached('{"news": []}', 'Sverige', 'Company A', '2026-10-03')
        first['issuer'] = 'Modified view'
        assert cached('{"news": []}', 'Sverige', 'Company A', '2026-10-03')['issuer'] == 'Company A'
        assert len(calls) == 1
        cached('{"news": []}', 'Sverige', 'Company B', '2026-10-03')
        cached('{"news": []}', 'Sverige', 'Company A', '2026-10-04')
        cached('{"news": [{"link": "new"}]}', 'Sverige', 'Company A', '2026-10-03')
        assert len(calls) == 4
    finally:
        cached.clear()


def test_ir_navigation_and_annual_meeting_are_not_financial_reports():
    from report_sources import candidate_report
    for title in ['Annual General Meeting', 'Delårsrapporter', 'Delårspresentationer', 'Årsredovisningar']:
        assert not candidate_report(title, '', 'https://www.investorab.com/')['is_financial_report']
    assert candidate_report('Annual report 2025', '', 'https://www.investorab.com/')['is_financial_report']
    assert candidate_report('Delårsrapport, 1 januari – 30 juni 2026', '', 'https://www.industrivarden.se/')['is_financial_report']


def test_non_report_news_cannot_hide_an_older_primary_report(monkeypatch):
    news = [{'title': 'Company A market update', 'link': URL + str(i),
             'published_at': '2026-07-16T08:00Z'} for i in range(12)]
    news.append({'title': 'Company A Q2 2026 report', 'link': URL + 'report', 'published_at': '2026-07-15T08:00Z'})
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return {'ok': True, 'text': body(), 'resolved_url': url}
    monkeypatch.setattr('report_fetcher.fetch_report_text', fetch)
    result = verify_primary_report_from_events({'news': news}, 'Sverige', company_name='Company A')
    assert result['Rapport läst'] is True
    assert calls == [URL + 'report']


def test_duplicate_urls_do_not_consume_report_attempts(monkeypatch):
    news = [{'title': 'Company A Q2 2026 report', 'link': URL + 'bad', 'published_at': '2026-07-16T08:00Z'}] * 12
    news.append({'title': 'Company A Q2 2026 report', 'link': URL + 'good', 'published_at': '2026-07-15T08:00Z'})
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return {'ok': True, 'text': body() if url.endswith('good') else 'Cookie page', 'resolved_url': url}
    monkeypatch.setattr('report_fetcher.fetch_report_text', fetch)
    result = verify_primary_report_from_events({'news': news}, 'Sverige', company_name='Company A')
    assert result['Rapport läst'] is True and len(calls) == 2


def test_failed_primary_link_can_fall_back_to_registered_issuer(monkeypatch):
    calls = []
    ir = 'https://www.investorab.com/report'
    monkeypatch.setattr('report_fetcher.discover_issuer_report_events',
                        lambda name, **kwargs: [{'title': 'Investor Q2 2026 report', 'link': ir}])
    def fetch(url, **kwargs):
        calls.append(url)
        return {'ok': True, 'text': body('Investor') if url == ir else 'Cookie page', 'resolved_url': url}
    monkeypatch.setattr('report_fetcher.fetch_report_text', fetch)
    news = [{'title': 'Investor Q2 2026 report', 'link': URL, 'published_at': '2026-07-15T08:00Z'}]
    result = verify_primary_report_from_events({'news': news}, 'Sverige', company_name='Investor AB ser. B')
    assert result['Rapport läst'] is True and calls == [URL, ir]


def test_request_budget_prevents_new_attempts_after_a_slow_failure(monkeypatch):
    clock = [100.0]
    calls = []
    monkeypatch.setattr('report_fetcher.time.monotonic', lambda: clock[0])
    def fetch(url, **kwargs):
        calls.append((url, kwargs['timeout']))
        clock[0] += 13
        return {'ok': False, 'text': '', 'error': 'Timed out'}
    monkeypatch.setattr('report_fetcher.fetch_report_text', fetch)
    news = [{'title': 'Company A Q2 2026 report', 'link': URL + str(i)} for i in range(8)]
    result = verify_primary_report_from_events({'news': news}, 'Sverige', company_name='Company A')
    assert result['Rapport läst'] is False
    assert len(calls) == 1 and calls[0][1] <= 8


def test_issuer_archive_discovers_reports_not_presentations_or_external_copies(monkeypatch):
    from report_fetcher import discover_issuer_report_events
    class Response:
        def __init__(self, url): self.url = url
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return self.url
        def read(self, limit):
            return b'<a href="/media/q2-2026.pdf">PDF Q2 Report</a><a href="/media/q2-slides.pdf">Q2 Presentation</a><a href="https://unknown.example/q2.pdf">Q2 Report</a><a href="/media/q2-2026.pdf">Q2 Report</a>'
    calls = []
    def open_url(request, **kwargs):
        calls.append(request.full_url)
        return Response(request.full_url)
    monkeypatch.setattr('report_fetcher.urlopen', open_url)
    result = discover_issuer_report_events('Investor AB ser. B')
    assert len(result) == 1 and result[0]['link'].endswith('/media/q2-2026.pdf')
    assert len(calls) == 1 and calls[0].rsplit('/', 1)[-1].isdigit()
    assert result[0]['published_at'] == ''  # Archive year is not a publication time.


def test_issuer_pdf_labels_preserve_archive_period_and_latest_first(monkeypatch):
    from report_fetcher import discover_issuer_report_events
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def geturl(self): return 'https://www.industrivarden.se/investerare/rapporter-och-presentationer/Delarsrapporter/'
        def read(self, limit):
            return b'<a href="/2025_q4.pdf">2025 12M</a><a href="/2026_q1.pdf">2026 3M</a><a href="/2026_q2.pdf">2026 6M</a>'
    monkeypatch.setattr('report_fetcher.urlopen', lambda *args, **kwargs: Response())
    result = discover_issuer_report_events('Industrivärden, AB ser. C')
    assert [item['link'].split('/')[-1] for item in result] == ['2026_q2.pdf', '2026_q1.pdf', '2025_q4.pdf']
    assert all(item['title'].startswith('Delårsrapport ') and item['published_at'] == '' for item in result)
