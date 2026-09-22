from decision_brief import build_decision_brief


def test_brief_uses_existing_evidence_without_new_score():
    result = build_decision_brief({
        "Signal": "KÖP NU",
        "Signal kort": "Tidigt köpläge",
        "Varför köpa": "KPI förbättras före kursen.",
        "Market-Implied Expectations": "💎 Låga förväntningar börjar överträffas",
        "Market-Implied Expectations förklaring": "Låg börda och flera förbättringar.",
        "Market Blind Spot reasons": "låg verifierad bevakning",
        "Catalyst-to-Recognition reasons": "rapport inom en månad",
        "Recognition Window": "⚡ Recognition sannolikt nära",
        "Recognition Window payoff": "🟢 Attraktiv observerad uppsida relativt väntetiden",
        "Största risk": "marginalen viker",
        "Vad ändrar Borsifys syn": "sänkt guidance",
        "Analysis Confidence": "🟢 Gott",
    })
    assert result["Decision Brief beslut"] == "KÖP NU"
    assert result["Decision Brief market wrong"] == "låg verifierad bevakning"
    assert result["Decision Brief expectations"] == "Priset verkar inte kräva att allt går perfekt för bolaget."
    assert not any("Score" in key for key in result)


def test_missing_evidence_is_exposed_not_invented():
    result = build_decision_brief({})
    assert "kan inte säkert förklara" in result["Decision Brief market wrong"]
    assert "ingen tydlig händelse" in result["Decision Brief recognition"]
    assert "vet inte när" in result["Decision Brief timing"]


def test_app_wires_brief_after_recognition_without_ranking_effect():
    app = open("app.py", encoding="utf-8").read()
    rankings = open("horizon_rankings.py", encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "add_decision_briefs(ranked)" in app
    assert "Decision Brief" not in rankings
