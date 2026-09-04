from pathlib import Path

APP=(Path(__file__).resolve().parents[1]/"app.py").read_text(encoding="utf-8")

def test_version_is_262_or_newer():
    assert 'APP_VERSION = "2.61.0"' not in APP

def test_primary_cards_use_one_named_main_score():
    assert 'st.metric("Borsifys huvudbetyg"' not in APP
    assert 'st.metric("Borsifys betyg för tidshorisonten"' in APP

def test_short_discover_no_longer_shows_four_parallel_metrics():
    assert 's1, s2 = st.columns([4.0, 1.0])' in APP
    assert 's3.metric("Hur bra underlaget är"' not in APP
    assert 's4.metric("Relativ styrka"' not in APP
    assert 's5.metric("Bekräftelser"' not in APP

def test_long_discover_moves_diagnostics_behind_expander():
    assert 'with st.expander("Visa delbedömningar"):' in APP
    assert 'c.metric("Risk för värdefälla"' not in APP
    assert 'd.metric("Har utvecklingen vänt?"' not in APP
    assert 'f.metric("Hur bra underlaget är"' not in APP

def test_readiness_is_label_first_on_horizon_cards():
    assert 'st.caption(f"Underlaget: {readiness_status}' in APP
    assert 'st.success(f"{readiness_status} · {readiness:.0f}/100")' not in APP
    assert 'with st.expander("Visa mer om bedömningen", expanded=False):' in APP

def test_secondary_numeric_evidence_remains_available():
    assert '"Underlagets detaljpoäng": case.get("Short Alpha Confidence", "—")' in APP
    assert '"Oberoende stöd": evidence_preview' in APP
