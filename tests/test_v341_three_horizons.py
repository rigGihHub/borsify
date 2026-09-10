from pathlib import Path
import pandas as pd
from horizon_rankings import add_horizon_scores, top_ranked

APP = Path(__file__).resolve().parents[1].joinpath('app.py').read_text(encoding='utf-8')

def sample():
    rows=[]
    for i in range(12):
        rows.append({
            'Ticker':f'T{i}.ST','Namn':f'Bolag {i}','INVEST Score':80-i/3,'Kvalitet':82-i/4,'Risk':80-i/5,
            'Värdering':75-i/4,'ROE':.18,'Vinstmarginal':.14,'Omsättningstillväxt':.08,
            '1 mån':.05,'3 mån':.10,'6 mån':.15,'Dagsförändring':.01,'Volymkvot':1.2,'RSI14':60,'Avstånd SMA200':.08,
            'Datatäckning':.95,'Pris':100+i,'Valuta':'SEK','Börsvärde BSEK':20,'Omsättning MSEK/dag':20,
            'Skuld/eget kapital':.4,'P/E':18,'Direktavkastning':.02
        })
    return pd.DataFrame(rows)

def test_year_score_exists_and_is_bounded():
    out=add_horizon_scores(sample())
    assert 'Års Score' in out.columns
    assert out['Års Score'].between(0,100).all()

def test_app_has_three_clear_user_categories_and_top_ten():
    assert 'Köp nu – sälj i närtid' in APP
    assert 'Äg upp till ett år' in APP
    assert 'Äg resten av livet' in APP
    assert 'Topp 10 i kategorin' in APP
    assert 'top_ranked(filtered, horizon, limit=10)' in APP
