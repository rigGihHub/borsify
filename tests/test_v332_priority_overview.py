from pathlib import Path

APP = Path("app.py").read_text(encoding="utf-8")


def test_version():
    assert 'APP_VERSION = "4.39.2"' in APP


def test_overview_has_one_clear_first_choice():
    assert 'Förstaval' in APP
    assert 'Borsifys starkaste köpförslag just nu.' in APP


def test_secondary_choices_are_compact():
    assert 'ALTERNATIV' in APP
    assert 'st.caption(f"{ticker}{score_text}")' in APP


def test_secondary_tools_are_collapsed_together():
    assert 'with st.expander("Fler val och verktyg", expanded=False)' in APP
    assert '**Öppna en annan aktie**' in APP
