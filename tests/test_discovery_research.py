from datetime import datetime, timezone
import pytest
from discovery_research import research_report, ISSUERS
from issuer_report_sources import verified_issuer_url, source_for_issuer
from report_sources import candidate_report
from report_verification import verify_report_text


URL = 'https://ir.asteralabs.com/test-q2-2026'
BODY = ('Astera Labs Q2 2026 financial results. Revenue $100 million. Profit $20 million. '
        'Customers increased 10 percent, but recurring revenue declined in one segment. '
        'Competition increased and demand remains uncertain. '
        + 'The company describes financial reporting policies and quarterly operations. ' * 30)


def checked_report(body=BODY, url=URL, name='Astera Labs', title='Q2 2026 results'):
    candidate = {**candidate_report(title, '2026-08-04', url), 'issuer_name': name}
    return verify_report_text(candidate, '', body, company_name=name)


def test_unknown_symbol_never_causes_network_fetch():
    result = research_report('UNKNOWN', lambda *a, **k: pytest.fail('unexpected network'))
    assert result['status'] == 'Källa saknas'


@pytest.mark.parametrize('report', [None, {}, {'Rapport läst': True}, checked_report(body='Astera Labs')])
def test_missing_or_unverified_report_never_becomes_research_success(report):
    assert research_report('ALAB', lambda *a, **k: report)['status'] == 'Inte verifierad'


def test_checked_report_preserves_negative_wording_and_source_without_upgrading_moat():
    result = research_report('ALAB', lambda *a, **k: checked_report())
    assert result['status'] == 'Rapporttext kontrollerad'
    assert result['url'] == URL
    assert result['publication_verified'] is False
    assert any('declined' in e['text'] for e in result['excerpts'])
    assert all(e['källa'] == URL for e in result['excerpts'])
    assert sum(len(e['text'].split()) for e in result['excerpts']) <= 160
    assert len(result['excerpts']) <= 4
    assert 'inte oberoende' in result['limits']
    assert 'Score' not in result


def test_reader_is_issuer_bound_and_has_finite_budget():
    calls = []
    def reader(events, country, **kwargs):
        calls.append((events, kwargs))
        return None
    research_report('ALAB', reader)
    events, kwargs = calls[0]
    assert kwargs['company_name'] == 'Astera Labs'
    assert kwargs['budget_seconds'] == 12
    assert events['news'] and all(verified_issuer_url(item['link'], kwargs['company_name']) for item in events['news'])


def test_timeout_has_explicit_failure_status():
    def timeout(*args, **kwargs):
        raise TimeoutError()
    assert research_report('ALAB', timeout)['status'] == 'Hämtning misslyckades'


def test_all_registered_discovery_issuers_have_exact_trusted_domains():
    for name in ISSUERS.values():
        source = source_for_issuer(name)
        assert source is not None
        assert verified_issuer_url(source['index'], name)
        assert not verified_issuer_url('https://evil.example/?issuer=' + name, name)


def test_wrong_issuer_body_and_redirect_domain_are_not_accepted():
    assert checked_report(name='Credo Technology')['Rapport läst'] is False
    assert checked_report(url='https://ir.asteralabs.com.evil.example/report')['Rapport läst'] is False


def test_fiscal_quarter_period_is_verified_without_inventing_calendar_year():
    report = checked_report(body=BODY.replace('Q2 2026', 'Q2 FY2027'), title='Q2 FY2027 results')
    assert report['Rapport läst'] is True
    assert report['Rapport periodtext'] == 'Q2 FY2027'


def test_spelled_quarter_matches_title_and_rejects_wrong_quarter():
    body = BODY.replace('Q2 2026', 'Second quarter 2026')
    assert checked_report(body=body)['Rapport läst'] is True
    assert checked_report(body=body, title='Q3 2026 results')['Rapport läst'] is False
