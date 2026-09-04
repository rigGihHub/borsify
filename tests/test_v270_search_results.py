from pathlib import Path
import pandas as pd

from search_explanation import (
    intent_match_reason, horizon_match_reason, requirement_statuses,
    main_risk_text, data_status_text, near_miss_reason,
)

APP = Path('app.py').read_text(encoding='utf-8')


def test_version_and_search_result_ui_present():
    assert 'APP_VERSION = "2.80.0"' in APP
    assert 'st.subheader("Matchar din sökning")' in APP
    assert 'Varför den passar' in APP
    assert 'Viktigaste risk' in APP
    assert 'Varför fick en annan aktie inte plats?' in APP
    assert 'Pris SEK' in APP


def test_explanations_are_grounded_and_plain():
    row = pd.Series({
        'Borsify Score': 72, 'INVEST Score': 75, 'Kvalitet': 78, 'Risk': 62,
        'Lång Score': 74, 'Datatäckning': .85, 'Riskflaggor': 'Hög skuldsättning',
    })
    assert 'starkt' in intent_match_reason(row, 'Bra långsiktig investering')
    assert '1–5 år' in horizon_match_reason(row, '1–5 år')
    assert any('Data: klarar' in x for x in requirement_statuses(row, '1–5 år'))
    assert main_risk_text(row) == 'Hög skuldsättning'
    assert data_status_text(row) == 'Bra datatäckning'
    assert 'rankades högre' in near_miss_reason(row, 'Bästa möjligheter just nu', '1–5 år')


def test_missing_data_is_not_invented():
    row = pd.Series({'Datatäckning': float('nan')})
    assert 'saknar' in intent_match_reason(row, 'Bra långsiktig investering')
    assert data_status_text(row) == 'Datastatus oklar'
    assert 'Ingen enskild huvudrisk' in main_risk_text(row)
