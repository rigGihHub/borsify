from why_now_engine import build_why_now_assessment


def test_two_independent_fresh_families_make_clear_why_now():
    case = {
        "Förväntningsriktning": "positiv", "Förväntningsförändring": "Förväntningarna förbättras med stöd i siffrorna",
        "Förväntning reported direction": 1, "Förväntning analyst direction": 1,
        "Post-report stöd": True, "Post-report dagar sedan": 12, "Post-report status": "Positiv drift",
        "Catalyst Independent Support": False,
    }
    out = build_why_now_assessment(case)
    assert out["Why Now Status"] == "Tydligt varför nu"
    assert out["Why Now Evidence Count"] == 2


def test_old_post_report_does_not_count_as_fresh_support():
    out = build_why_now_assessment({"Post-report stöd": True, "Post-report dagar sedan": 45})
    assert out["Why Now Evidence Count"] == 0
    assert out["Why Now Status"] == "Inget tydligt varför nu"


def test_independent_catalyst_is_separate_but_data_inflection_is_not_double_counted():
    out = build_why_now_assessment({
        "Förväntningsriktning": "positiv_tidigt", "Förväntning reported direction": 1,
        "Catalyst Independent Support": True, "Primary Catalyst": "Order/kontrakt", "Catalyst Timing": "idag",
    })
    assert out["Why Now Evidence Count"] == 2
    assert "Oberoende katalysator" in out["Why Now Evidence Families"]


def test_negative_change_is_visible_and_cannot_become_clear_positive():
    out = build_why_now_assessment({
        "Förväntningsriktning": "negativ", "Förväntningsförändring": "Förväntningarna sänks",
        "Catalyst Signal": "Ny risk måste verifieras först",
    })
    assert out["Why Now Status"] == "Motbevis väger tyngre"
    assert out["Why Now Contradiction Count"] >= 1


def test_no_new_score_or_automatic_gate_language():
    import inspect, why_now_engine
    src = inspect.getsource(why_now_engine)
    assert 'Why Now Score' not in src
    assert 'auto' not in src.lower()
