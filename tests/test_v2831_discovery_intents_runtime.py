from pathlib import Path

APP = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")


def test_discovery_intents_is_defined_before_sidebar_uses_it():
    definition = APP.index("DISCOVERY_INTENTS = [")
    use = APP.index('"Typ av case", DISCOVERY_INTENTS')
    assert definition < use


def test_discovery_intents_contains_all_supported_search_goals():
    for label in [
        "Bästa möjligheter just nu",
        "Bra långsiktig investering",
        "Utdelningsaktier",
        "Billiga kvalitetsbolag",
        "Aktier som fallit mycket",
        "Kortsiktigt köpläge",
        "Stabilare aktier",
    ]:
        assert f'"{label}"' in APP
