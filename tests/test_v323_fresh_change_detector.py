from fresh_change_detector import build_fresh_change


def test_detects_new_positive_changes_not_just_good_levels():
    out = build_fresh_change({
        "Omsättning YoY senaste kvartal": .12, "Omsättning YoY föregående kvartal": -.01,
        "Marginal YoY förändring": .025, "Marginal YoY föregående kvartal": .005,
        "FCF YoY senaste kvartal": .05, "FCF YoY föregående kvartal": .02,
        "Vinst YoY senaste kvartal": .08, "Vinst YoY föregående kvartal": .05,
    })
    assert out["Fresh Change Status"] == "Flera färska förbättringar"
    assert out["Fresh Change Positive Count"] == 2


def test_continuing_strength_is_not_called_fresh_change():
    out = build_fresh_change({
        "Omsättning YoY senaste kvartal": .10, "Omsättning YoY föregående kvartal": .09,
        "Marginal YoY förändring": .03, "Marginal YoY föregående kvartal": .025,
    })
    assert out["Fresh Change Status"] == "Ingen ny tydlig förändring"
    assert out["Fresh Change Positive Count"] == 0


def test_negative_change_is_visible_and_not_averaged_away():
    out = build_fresh_change({
        "Omsättning YoY senaste kvartal": -.08, "Omsättning YoY föregående kvartal": .05,
        "Marginal YoY förändring": .03, "Marginal YoY föregående kvartal": .0,
    })
    assert out["Fresh Change Status"] == "Ny försämring upptäckt"
    assert out["Fresh Change Negative Count"] >= 1


def test_missing_prior_history_stays_insufficient():
    out = build_fresh_change({"Omsättning YoY senaste kvartal": .20})
    assert out["Fresh Change Status"] == "För lite jämförbar historik"


def test_no_fresh_change_score_exists():
    out = build_fresh_change({})
    assert "Fresh Change Score" not in out
