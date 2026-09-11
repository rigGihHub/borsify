from pathlib import Path
import pandas as pd

from estimate_revision_radar import assess_estimate_revision, add_estimate_revision_radar, select_estimate_revision_candidates
from finalist_selection import select_deep_finalist_pool


def _row(**kw):
    base = {
        "Ticker": "AAA.ST", "EPS-estimat förändring": .06, "EPS-revisionsbalans": .60,
        "Estimat tillförlitlighetsvikt": .75, "Analytiker antal": 6,
        "Reviderande analytiker senaste period": 4, "1 mån": .03,
        "INVEST Score": 60, "Kvalitet": 60, "Daytrade Score": 60, "Livstid Score": 60, "Datatäckning": 80,
        "REVERSAL Score": 50, "Värdering": 60, "Lång Score": 60,
        "Mellan Score": 60, "Års Score": 60,
    }
    base.update(kw)
    return base


def test_broad_positive_revisions_with_muted_price_are_flagged_without_new_score():
    out = assess_estimate_revision(_row())
    assert out["Estimat Radar kandidat"] is True
    assert out["Estimat Radar underreaktion"] is True
    assert "liten kursreaktion" in out["Estimat Radar status"]
    assert not any("score" in k.lower() for k in out)


def test_missing_coverage_and_sharp_price_fall_are_not_rewarded():
    thin = assess_estimate_revision(_row(**{"Estimat tillförlitlighetsvikt": .25}))
    falling = assess_estimate_revision(_row(**{"1 mån": -.20}))
    assert thin["Estimat Radar kandidat"] is False
    assert falling["Estimat Radar kandidat"] is False
    assert "svag kursreaktion" in falling["Estimat Radar status"]


def test_selector_prefers_underreaction_then_breadth_deterministically():
    df = pd.DataFrame([
        _row(Ticker="B.ST", **{"1 mån": .15, "EPS-revisionsbalans": .80}),
        _row(Ticker="A.ST", **{"1 mån": .02, "EPS-revisionsbalans": .50}),
        _row(Ticker="C.ST", **{"1 mån": .01, "EPS-revisionsbalans": .40, "Estimat tillförlitlighetsvikt": .45}),
    ])
    ranked = select_estimate_revision_candidates(add_estimate_revision_radar(df), quota=2)
    tickers = [df.loc[idx, "Ticker"] for idx, _ in ranked]
    assert tickers == ["A.ST", "C.ST"]


def test_finalist_pool_reserves_one_estimate_revision_doorway_after_incumbent_convictions():
    rows = [
        _row(Ticker="INV1.ST", **{"INVEST Score": 95}),
        _row(Ticker="INV2.ST", **{"INVEST Score": 90}),
        _row(Ticker="REV.ST", **{"INVEST Score": 50, "EPS-estimat förändring": .08, "EPS-revisionsbalans": .70, "1 mån": .02}),
        _row(Ticker="Q.ST", **{"INVEST Score": 70, "Kvalitet": 85, "EPS-estimat förändring": 0, "EPS-revisionsbalans": 0}),
    ]
    df = add_estimate_revision_radar(pd.DataFrame(rows))
    out = select_deep_finalist_pool(df, pool_size=3)
    assert out["Ticker"].tolist()[:2] == ["INV1.ST", "INV2.ST"]
    assert "REV.ST" in out["Ticker"].tolist()
    assert out.loc[out["Ticker"] == "REV.ST", "Djupurval Nyckel"].iloc[0] == "estimate_revision"


def test_v353_wiring_and_version():
    app = Path("app.py").read_text(encoding="utf-8")
    final = Path("finalist_selection.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "add_estimate_revision_radar" in app
    assert "Estimatförändringar i kandidatpoolen" in app
    assert "select_estimate_revision_candidates" in final
