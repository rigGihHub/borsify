import json
import pandas as pd

from prospective_signal_scorecard import (
    STATUS_REVIEW, STATUS_SUPPORT, STATUS_WAIT,
    build_prospective_signal_scorecard, scorecard_summary,
)


def _rec(i, version="3.76.0", date="2026-09-10", gap=False, under=False):
    snap = {
        "Expectation Gap kandidat": gap,
        "Expectation Gap varning": False,
        "Expectation Gap status": "Förbättring före förväntningarna" if gap else "Positiv förändring – inget tydligt expectation gap",
        "Expectation Gap analytiker antal": 8,
        "Förändringsbekräftelse kandidat": True,
        "Nyhetsförväntning": "positiv överraskning" if under else "",
        "Nyhetskälla styrka": "stark" if under else "",
        "Initial kursreaktion": 0.01 if under else None,
    }
    return {"record_id": f"r{i}", "symbol": f"S{i}", "captured_date": date, "horizon_type": "long", "snapshot_json": json.dumps(snap), "model_version": version}


def test_empty_scorecard_waits_and_keeps_all_hypotheses_visible():
    table = build_prospective_signal_scorecard(pd.DataFrame(), pd.DataFrame())
    assert len(table) == 8
    assert set(table["Status"]) == {STATUS_WAIT}
    assert "News Underreaction" in set(table["Hypotes"])
    assert "Expectation Gap" in set(table["Hypotes"])


def test_scorecard_never_turns_waiting_into_support_from_thin_data():
    recs = pd.DataFrame([_rec(1, gap=True)])
    outs = pd.DataFrame([{"record_id": "r1", "horizon": "1m", "return_pct": 0.2}])
    table = build_prospective_signal_scorecard(recs, outs)
    gap = table[table["Hypotes"].eq("Expectation Gap")].iloc[0]
    assert gap["Status"] == STATUS_WAIT
    assert int(gap["Största sample"]) == 1


def test_summary_prioritises_review_over_support():
    table = pd.DataFrame([
        {"Hypotes": "A", "Familj": "x", "Status": STATUS_SUPPORT, "Mogna horisonter": 1, "Största sample": 40, "Nästa steg": ""},
        {"Hypotes": "B", "Familj": "x", "Status": STATUS_REVIEW, "Mogna horisonter": 1, "Största sample": 40, "Nästa steg": ""},
    ])
    summary = scorecard_summary(table)
    assert summary["status"] == STATUS_REVIEW
    assert "granskas" in summary["text"].lower()


def test_app_contains_compact_signal_scorecard():
    app = open("app.py", encoding="utf-8").read()
    assert "Prospective Signal Scorecard" in app
    assert "vad håller för test" in app.lower()
