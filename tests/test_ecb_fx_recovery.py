from datetime import date
import ast
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from ecb_fx import parse_reference_rates
import data_acquisition as da

XML = '<Envelope><Cube><Cube time="2026-10-06"><Cube currency="SEK" rate="11.2425"/><Cube currency="NOK" rate="10.7780"/><Cube currency="DKK" rate="7.4747"/></Cube></Cube></Envelope>'


def test_ecb_cross_rates_use_sek_per_foreign_currency():
    rates, observed = parse_reference_rates(XML, today=date(2026,10,6))
    assert rates['SEK'] == 1
    assert rates['NOK'] == pytest.approx(11.2425/10.7780)
    assert rates['DKK'] == pytest.approx(11.2425/7.4747)
    assert observed == '2026-10-06'


@pytest.mark.parametrize('xml', [XML.replace('2026-10-06','2026-09-01'), XML.replace('2026-10-06','2026-10-07'), XML.replace('SEK','ZZZ')])
def test_invalid_ecb_data_is_rejected(xml):
    with pytest.raises(ValueError):parse_reference_rates(xml,today=date(2026,10,6))


def test_empty_yahoo_fx_recovers_without_overwriting_good_rates(monkeypatch):
    class T:
        def __init__(self,symbol):self.symbol=symbol
        def history(self,**kw):return pd.DataFrame({'Close':[10.]}) if self.symbol=='USDSEK' else pd.DataFrame()
    class YF:Ticker=T
    monkeypatch.setattr(da,'_yf',lambda:YF)
    monkeypatch.setattr(da,'fetch_reference_rates',lambda:({'NOK':1.05,'USD':9.9},'2026-10-06'))
    rates, health=da.fx_rates_to_sek(('USD','NOK'),{'USD':'USDSEK','NOK':'NOKSEK'},str)
    assert rates=={'SEK':1.,'USD':10.,'NOK':1.05}
    assert not health['missing']
    assert health['ecb_currencies']==['NOK']


def test_mixed_provider_frame_preserves_observed_fcf_ratio():
    tree=ast.parse(Path('app.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='add_sek_conversions')
    node.decorator_list=[]
    ns={'pd':pd,'np':np,'major_currency':str,'major_amount_to_sek':lambda v,c,r:v*r.get(c,np.nan),
        'quote_amount_to_sek':lambda v,c,r:v*r.get(c,np.nan),'fetch_fx_rates_to_sek':lambda c:{'SEK':1.,'NOK':1.05}}
    exec(compile(ast.Module(body=[node],type_ignores=[]),'app.py','exec'),ns)
    frame=pd.DataFrame([
        {'Valuta':'NOK','Finansiell valuta':'NOK','Fundamental reservkälla':True,'FCF-yield':.12,'_Raw marketCap':1000},
        {'Valuta':'SEK','Finansiell valuta':'SEK','FCF-yield':.1,'_Raw freeCashflow':100,'_Raw marketCap':1000}])
    result,_,missing=ns['add_sek_conversions'](frame)
    assert result['FCF-yield'].tolist()==pytest.approx([.12,.1])
    assert not missing
