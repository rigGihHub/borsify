from pathlib import Path
import numpy as np
import pandas as pd
from challenger_path import path_to_number_one, challenger_paths, _rank_dimensions


def test_final_score_precedes_raw_horizon_score():
    winner = {'Borsify slutbetyg': 74, 'Livstid Score': 79, 'Ticker': 'A'}
    challenger = {'Borsify slutbetyg': 70, 'Livstid Score': 92, 'Ticker': 'B'}
    result = path_to_number_one(winner, challenger, 'Livstid Score', 'lifetime')
    assert result['Första avgörande dimension'] == 'Borsify slutbetyg'
    assert result['Nuvarande gap'] == 4
    assert '92' not in result['Formell väg till #1']
    assert '79' not in result['Formell väg till #1']
    assert 'Kontrollera rankordningen' not in result['Formell väg till #1']


def test_equal_final_scores_explain_horizon_tiebreak_without_raw_score():
    result = path_to_number_one({'Borsify slutbetyg': 74, 'Års Score': 88}, {'Borsify slutbetyg': 74, 'Års Score': 82}, 'Års Score', 'year')
    assert 'samma Borsify slutbetyg' in result['Formell väg till #1']
    assert '88' not in result['Formell väg till #1']
    assert '82' not in result['Formell väg till #1']
    assert result['Tröskel'] == '—'


def test_specialist_cap_cannot_be_overcome_with_more_raw_points():
    result = path_to_number_one({'Borsify slutbetyg': 74}, {'Borsify slutbetyg': 68, 'Investmentbolag': True, 'Investmentbolag rankningstak': 68, 'Livstid Score': 92}, 'Livstid Score', 'lifetime')
    assert 'Ett högre grundbetyg räcker inte' in result['Formell väg till #1']
    assert result['Tröskel'] == '—'
    assert "Vid lika slutbetyg" not in result['Formell väg till #1']


def test_missing_final_score_cannot_fall_back_to_raw_score():
    result = path_to_number_one({'Borsify slutbetyg': 74, 'Års Score': 88}, {'Borsify slutbetyg': np.nan, 'Års Score': 92}, 'Års Score', 'year')
    assert 'saknas' in result['Formell väg till #1']
    assert result['Tröskel'] == '—'


def test_rank_dimensions_match_actual_horizon_sort_order():
    assert [item[0] for item in _rank_dimensions('Mellan Score', 'medium', True)] == ['Borsify slutbetyg', 'Mellan Score', 'Deal Conviction Score', 'Affärsläge rangvärde', 'Case Readiness', 'Relativ styrka', 'RR rangvärde', 'Datatäckning']
    assert [item[0] for item in _rank_dimensions('Års Score', 'year', True)] == ['Borsify slutbetyg', 'Års Score', 'Deal Conviction Score', 'Affärsläge rangvärde', 'Case Readiness', 'Datatäckning']


def test_toplist_visible_scores_use_final_score_and_no_raw_fallback():
    source = Path('app.py').read_text()
    assert 'table["Score"] = pd.to_numeric(table.get("Borsify slutbetyg", pd.Series(np.nan, index=table.index))' in source
    assert '"#", "Aktie", "Signal", "Borsify slutbetyg", "Förväntningar"' in source
    assert 'table["Score"] = pd.to_numeric(table.get(score_col)' not in source


def test_scale_maximum_allows_tie_but_never_an_impossible_threshold():
    result = path_to_number_one({'Borsify slutbetyg': 100}, {'Borsify slutbetyg': 98}, 'Års Score', 'year')
    assert result['Tröskel'] == '—'
    assert 'Vid lika slutbetyg' in result['Formell väg till #1']


def test_real_toplist_assignment_keeps_specialist_cap_and_missing_scores():
    import ast
    tree = ast.parse(Path('app.py').read_text())
    assignment = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign) and ast.unparse(node.targets[0]) == "table['Score']")
    table = pd.DataFrame({'Borsify slutbetyg': [68, np.nan], 'Livstid Score': [92, 95]})
    exec(compile(ast.Module(body=[assignment], type_ignores=[]), 'app.py', 'exec'), {'table': table, 'pd': pd, 'np': np, 'score_col': 'Livstid Score'})
    assert table['Score'].iloc[0] == 68
    assert pd.isna(table['Score'].iloc[1])


def test_hot_deploy_guard_loads_correct_ranking_helper(monkeypatch):
    import ast
    import challenger_path
    monkeypatch.delattr(challenger_path, 'FINAL_SCORE_RANKING')
    tree = ast.parse(Path('app.py').read_text())
    start = next(i for i, node in enumerate(tree.body) if isinstance(node, ast.Import) and any(alias.asname == '_challenger_path_module' for alias in node.names))
    nodes = tree.body[start - 1:start + 3]
    scope = {}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'app.py', 'exec'), scope)
    assert challenger_path.FINAL_SCORE_RANKING is True
    assert scope['challenger_paths'] is challenger_path.challenger_paths
