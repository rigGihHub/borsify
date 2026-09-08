from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")

def test_main_navigation_keeps_model_diagnostics_out_of_primary_pages():
    assert '["Idag", "Fler aktier", f"Bevakning ({len(watch_df_global)})", "Mer"]' in APP
    assert '"Analysera"' not in APP.split('page = st.radio', 1)[1].split('if page == "Överblick"', 1)[0]

def test_analysis_lab_is_explicitly_separated_from_user_flow():
    assert 'st.tabs(["Alla aktier", "Så fungerar Borsify", "Analyslabbet"])' in APP
    assert 'Här granskas Borsifys egna modeller och historik. Du behöver inte använda detta för att hitta aktier.' in APP
    assert 'Resultaten här är modellkontroller – inte köpsignaler.' in APP

def test_historical_edge_lab_lives_in_analysis_lab():
    lab_pos = APP.index('with more_lab:')
    render_pos = APP.index('render_edge_lab(default_edge_symbol', lab_pos)
    assert render_pos > lab_pos
