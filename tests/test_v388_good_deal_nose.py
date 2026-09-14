from good_deal import assess_good_deal


def base(**kw):
    x={
        'Kvalitet':82,'Risk':72,'Värdering':74,
        'Bolagsbedömning nivå':'green','Ingångsläge nivå':'green',
        '1 mån':.08,'3 mån':.16,'Avstånd SMA200':.08,'RSI14':62,
        'Expectation Gap kandidat':True,'Expectation Gap stark':False,
        'Crowded varning':False,'Crowded stark varning':False,
        'Riktkurs potential':.22,
        'Förändringsbekräftelse positiva familjer antal':2,
    }
    x.update(kw); return x


def test_strong_asymmetry_needs_value_change_and_clean_entry():
    r=assess_good_deal(base(),'year')
    assert r['Affärsläge nivå'] == 3
    assert 'Stark affärsasymmetri' in r['Affärsläge']


def test_crowded_expensive_case_is_not_called_bargain():
    r=assess_good_deal(base(**{'Crowded varning':True,'Crowded stark varning':True,'Värdering':28,'Riktkurs potential':.02}),'year')
    assert r['Affärsläge nivå'] == 0


def test_chased_price_blocks_good_deal_label():
    r=assess_good_deal(base(**{'1 mån':.42,'3 mån':.70,'Avstånd SMA200':.32,'RSI14':86}),'year')
    assert r['Affärsläge nivå'] == 0


def test_plain_good_company_without_underpricing_is_not_a_fynd():
    r=assess_good_deal(base(**{'Expectation Gap kandidat':False,'Värdering':52,'Riktkurs potential':.07,'Förändringsbekräftelse positiva familjer antal':1}),'year')
    assert r['Affärsläge nivå'] <= 1


def test_app_exposes_deal_nose_and_release():
    app=open('app.py',encoding='utf-8').read()
    ranks=open('horizon_rankings.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.35.0"' in app
    assert '"God affär"' in app
    assert '"Affärsläge"' in app
    assert 'Affärsläge rangvärde' in ranks
