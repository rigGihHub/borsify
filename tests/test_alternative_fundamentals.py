from datetime import datetime, timezone
import math
import pytest
import fundamental_acquisition as fa
from stockanalysis_fundamentals import listing, parse_statistics
from fundamental_cache import get_cached_fundamentals
from analyst_case import analyst_case

NOW = datetime(2026, 10, 6, tzinfo=timezone.utc)

def page(identity='STO:VOLV.B', currency='SEK', date='Oct 6, 2026'):
    rows={'PE Ratio':'17.88','Forward PE':'12.52','EV / EBITDA':'14.83','PB Ratio':'3.63',
          'Debt / Equity':'1.47','Return on Equity (ROE)':'20.88%','Profit Margin':'7.60%',
          'FCF Yield':'5.08%','Dividend Yield':'4.13%','Market Cap':'640.89B',
          'Revenue Growth Forecast (3Y)':'6.39%','Payout Ratio':'14.18%'}
    return f'<title>AB Volvo ({identity}) Statistics</title><p>Currency is {currency}</p><p>Last updated: {date}</p><table>'+''.join(f'<tr><td>{k}</td><td>{v}</td></tr>' for k,v in rows.items())+'</table>'


def test_exact_listing_mapping():
    assert listing('VOLV-B.ST')[:3] == ('sto','VOLV.B','SEK')
    assert listing('EQNR.OL')[:3] == ('osl','EQNR','NOK')
    assert listing('NOVO-B.CO')[:3] == ('cph','NOVO.B','DKK')
    assert listing('AAA') is None
    assert listing('../bad.ST') is None


def test_units_and_growth_semantics():
    p=parse_statistics(page(), 'VOLV-B.ST', now=NOW)
    assert p['ROE'] == pytest.approx(.2088)
    assert p['Skuld/eget kapital'] == 147
    assert p['Direktavkastning'] == pytest.approx(.0413)
    assert p['Börsvärde lokal mdr'] == pytest.approx(640.89)
    assert p['FCF-yield'] == pytest.approx(.0508)
    assert math.isnan(p['Omsättningstillväxt'])
    assert 'Rapportdatum' not in p
    assert p['Fundamental källdatum'] == '2026-10-06'


@pytest.mark.parametrize('html', [page(identity='STO:VOLCAR.B'), page(currency='USD'), page(date='Sep 1, 2026'), page(date='Oct 7, 2026'), page().replace('Last updated:', 'Unknown date:')])
def test_wrong_identity_currency_or_stale_data_is_rejected(html):
    with pytest.raises(ValueError):parse_statistics(html,'VOLV-B.ST',now=NOW)


def test_no_core_facts_is_not_a_success():
    with pytest.raises(ValueError):parse_statistics('<title>AB Volvo (STO:VOLV.B)</title>Currency is SEK Last updated: Oct 6, 2026','VOLV-B.ST',now=NOW)


def test_yahoo_outage_recovers_from_alternative_and_reuses_cache(monkeypatch, tmp_path):
    class T:
        def get_info(self):return {}
        info={}
    class YF:
        Ticker=staticmethod(lambda symbol:T())
    monkeypatch.setattr(fa,'_yf',lambda:YF)
    p=parse_statistics(page(),'VOLV-B.ST',now=NOW)
    calls=[]
    def fallback(symbol):
        calls.append(symbol)
        return p,{'source':p['Fundamental källa'],'status':'PARTIAL','errors':[]}
    monkeypatch.setattr(fa,'fetch_stockanalysis',fallback)
    db=tmp_path/'x.db'
    result,health=fa.fetch_fundamentals('VOLV-B.ST',db,str)
    assert result['P/E']==17.88 and health['status']=='PARTIAL'
    assert health['cache']=='ALTERNATIVE'
    assert get_cached_fundamentals(db,'VOLV-B.ST')['Fundamental käll-URL']==p['Fundamental käll-URL']
    result,health=fa.fetch_fundamentals('VOLV-B.ST',db,str)
    assert len(calls)==1 and health['cache']=='HIT'
    assert health['status']=='PARTIAL'
    thesis,_,_=analyst_case(result)
    assert 'Källa: Stock Analysis' in thesis
    assert 'Källa: Yahoo' not in thesis
