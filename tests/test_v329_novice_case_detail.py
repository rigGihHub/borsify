from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")

def test_version_and_novice_first_case_copy():
    assert 'APP_VERSION = "3.38.0"' in APP
    assert 'st.markdown("**Varför nu?**")' in APP
    assert '**Största risken**' in APP
    assert 'Visa analysen bakom' in APP
    assert 'Visa kortsiktiga delsignaler och underlag' not in APP

def test_advanced_short_case_content_is_collapsed():
    marker = 'with st.expander("Visa analysen bakom", expanded=False):'
    assert marker in APP
    tail = APP.split(marker, 1)[1][:3500]
    assert '"Datakvalitet": case.get("Data Trust status", "—")' in tail
    assert 'render_case_plan(case)' in tail
    assert 'render_case_ai_qa(case, qa_horizon, rank)' in tail
