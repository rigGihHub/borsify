import pandas as pd

from prospective_signal_scorecard import STATUS_REVIEW, STATUS_SUPPORT, STATUS_MIXED, STATUS_WAIT
from research_kill_promote_queue import (
    ACTION_REVIEW, ACTION_PROMOTE, ACTION_COLLECT,
    build_research_queue, research_queue_summary,
)


def _row(name, status, horizons, sample):
    return {"Hypotes": name, "Familj": "Test", "Status": status, "Mogna horisonter": horizons, "Största sample": sample, "Nästa steg": ""}


def test_review_is_always_first_and_never_auto_killed():
    score = pd.DataFrame([
        _row("Lovande", STATUS_SUPPORT, 3, 60),
        _row("Svag", STATUS_REVIEW, 2, 40),
    ])
    q = build_research_queue(score)
    assert q.iloc[0]["Åtgärd"] == ACTION_REVIEW
    assert "automatisk borttagning" in q.iloc[0]["Nästa kontroll"].lower()


def test_promotion_review_requires_both_horizons_and_sample():
    score = pd.DataFrame([
        _row("Mogen", STATUS_SUPPORT, 2, 30),
        _row("Tunt sample", STATUS_SUPPORT, 3, 29),
        _row("En horisont", STATUS_SUPPORT, 1, 100),
    ])
    q = build_research_queue(score)
    actions = dict(zip(q["Hypotes"], q["Åtgärd"]))
    assert actions["Mogen"] == ACTION_PROMOTE
    assert actions["Tunt sample"] == ACTION_COLLECT
    assert actions["En horisont"] == ACTION_COLLECT


def test_wait_and_mixed_collect_more_data():
    q = build_research_queue(pd.DataFrame([
        _row("A", STATUS_WAIT, 0, 0),
        _row("B", STATUS_MIXED, 2, 50),
    ]))
    assert set(q["Åtgärd"]) == {ACTION_COLLECT}


def test_summary_prioritises_review_over_promotion():
    q = pd.DataFrame([
        {"Åtgärd": ACTION_PROMOTE},
        {"Åtgärd": ACTION_REVIEW},
        {"Åtgärd": ACTION_COLLECT},
    ])
    assert research_queue_summary(q)["status"] == ACTION_REVIEW


def test_app_contains_research_queue_and_release_version():
    app = open("app.py", encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Research Kill/Promote Queue" in app
    assert "build_research_queue(signal_scorecard)" in app
