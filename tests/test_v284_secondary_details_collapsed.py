from pathlib import Path

APP = (Path(__file__).parents[1] / "app.py").read_text(encoding="utf-8")


def test_v284_version():
    assert 'APP_VERSION = "3.26.0"' in APP


def test_secondary_diagnostics_are_not_in_first_view_of_toplist_card():
    start = APP.index('st.markdown("**Varför köpa?**")', APP.index("def render_horizon_toplists"))
    expander = APP.index('with st.expander("Visa mer om bedömningen", expanded=False):', start)
    first_view = APP[start:expander]
    for heading in (
        "**Går aktien rimligt att handla?**",
        "**Marknadsläget**",
        "**Jämfört med marknaden och sektorn**",
        "**Risk jämfört med möjlig uppsida**",
    ):
        assert heading not in first_view


def test_secondary_diagnostics_remain_available_in_expander():
    expander = APP.index('with st.expander("Visa mer om bedömningen", expanded=False):', APP.index("def render_horizon_toplists"))
    end = APP.index("# Also surface the strongest candidates", expander)
    details = APP[expander:end]
    assert "Fördjupning: handel, marknad, jämförelser och riskplan." in details
    for heading in (
        "**Går aktien rimligt att handla?**",
        "**Marknadsläget**",
        "**Jämfört med marknaden och sektorn**",
        "**Risk jämfört med möjlig uppsida**",
    ):
        assert heading in details
