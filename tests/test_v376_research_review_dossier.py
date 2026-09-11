import pandas as pd

from research_kill_promote_queue import ACTION_REVIEW, ACTION_PROMOTE
from research_review_dossier import (
    CHECK_PENDING, DECISION_HOLD, DECISION_REVIEW,
    build_review_dossiers, dossier_summary,
)


def _q(name, action, status="Preliminärt stöd", horizons=2, sample=30):
    return {"Prioritet": 1, "Åtgärd": action, "Hypotes": name, "Familj": "Test", "Status": status, "Mogna horisonter": horizons, "Största sample": sample, "Varför": "", "Nästa kontroll": ""}


def test_dossier_only_includes_reviewable_actions():
    q = pd.DataFrame([
        _q("A", ACTION_REVIEW, "Behöver granskas"),
        _q("B", ACTION_PROMOTE),
        _q("C", "Samla mer data"),
    ])
    d = build_review_dossiers(q)
    assert set(d["Hypotes"]) == {"A", "B"}


def test_unmeasured_robustness_checks_are_never_invented():
    d = build_review_dossiers(pd.DataFrame([_q("A", ACTION_PROMOTE, horizons=3, sample=80)]))
    row = d.iloc[0]
    assert row["Regimrobusthet"] == CHECK_PENDING
    assert row["Signalöverlapp"] == CHECK_PENDING
    assert row["Kostnad/omsättning"] == CHECK_PENDING
    assert row["Datakvalitet"] == CHECK_PENDING


def test_negative_hypothesis_is_held_not_auto_killed():
    d = build_review_dossiers(pd.DataFrame([_q("Svag", ACTION_REVIEW, "Behöver granskas", 3, 80)]))
    assert d.iloc[0]["Rekommendation"] == DECISION_HOLD
    assert "inte för automatisk kill" in d.iloc[0]["Evidensläge"]


def test_promotion_candidate_is_review_only_not_approval():
    d = build_review_dossiers(pd.DataFrame([_q("Stark", ACTION_PROMOTE, horizons=3, sample=80)]))
    assert d.iloc[0]["Rekommendation"] == DECISION_REVIEW
    assert "inte produktionsgodkänd" in d.iloc[0]["Evidensläge"]


def test_summary_prioritises_negative_review():
    d = build_review_dossiers(pd.DataFrame([_q("Stark", ACTION_PROMOTE), _q("Svag", ACTION_REVIEW, "Behöver granskas")]))
    assert dossier_summary(d)["status"] == ACTION_REVIEW


def test_app_contains_dossier_and_release_version():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Research Review Dossier" in app
    assert "build_review_dossiers(research_queue)" in app
