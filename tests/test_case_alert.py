import pandas as pd

from case_alert import evaluate_case_alert


def test_profit_warning_plus_weaker_journal_becomes_high_priority_review():
    out = evaluate_case_alert(
        {"status": "Borsifys mätbild har försvagats", "tone": "negative", "score_delta": -8},
        {"status": "Caset håller enligt dina regler", "tone": "positive", "triggered": []},
        pd.Series({
            "Huvudhändelse": "Vinstvarning / tydlig försämring",
            "Case Impact": "Ny risk – kontrollera direkt",
            "Case Impact Nivå": 3,
            "Mediepuls": "Ökad uppmärksamhet",
        }),
    )
    assert out["status"] == "Granska nu"
    assert out["priority"] == 3
    assert "inte en automatisk säljorder" in out["summary"]


def test_ambiguous_report_does_not_get_guessed_negative():
    out = evaluate_case_alert(
        {"status": "Borsifys mätbild är ungefär oförändrad", "tone": "neutral", "score_delta": 1},
        {"status": "Caset håller enligt dina regler", "tone": "positive", "triggered": []},
        {
            "Huvudhändelse": "Rapport / resultat",
            "Case Impact": "Kan ändra investeringscaset",
            "Case Impact Nivå": 3,
            "Mediepuls": "Nytt omnämnande",
        },
    )
    assert out["status"] == "Ny viktig bolagshändelse"
    assert out["priority"] == 1
    assert "gissar inte riktningen" in out["summary"]


def test_triggered_breaker_without_media_still_needs_review():
    out = evaluate_case_alert(
        {"status": "Borsifys mätbild är ungefär oförändrad", "tone": "neutral", "score_delta": -1},
        {"status": "Case-breaker utlöst", "tone": "negative", "triggered": ["Kvalitet under gräns"]},
        None,
    )
    assert out["status"] == "Case-breaker utlöst"
    assert out["priority"] == 2


def test_media_pulse_without_internal_weakness_is_only_an_idea():
    out = evaluate_case_alert(
        {"status": "Borsifys mätbild är ungefär oförändrad", "tone": "neutral", "score_delta": 0},
        {"status": "Caset håller enligt dina regler", "tone": "positive", "triggered": []},
        {
            "Huvudhändelse": "Forumdiskussion",
            "Case Impact": "Brus tills orsaken är verifierad",
            "Case Impact Nivå": 0,
            "Mediepuls": "Aktivt just nu",
            "Omnämnanden 24h": 3,
            "Mediekällor": 0,
        },
    )
    assert out["priority"] == 0
    assert out["status"] == "Nytt att läsa – inget internt larm"
