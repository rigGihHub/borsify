from __future__ import annotations

from pathlib import Path
import pandas as pd

from consensus_change_engine import build_consensus_change, select_consensus_change_candidates


def _summary(current=(4, 5, 2, 0, 0), previous=(2, 4, 5, 0, 0)):
    cols = ["strongBuy", "buy", "hold", "sell", "strongSell"]
    return pd.DataFrame([
        {"period": "0m", **dict(zip(cols, current))},
        {"period": "-1m", **dict(zip(cols, previous))},
    ])


def _actions(up=0, down=0, init=0):
    rows = []
    d = pd.Timestamp("2026-09-01")
    for i in range(up): rows.append({"GradeDate": d, "Firm": f"U{i}", "Action": "up"})
    for i in range(down): rows.append({"GradeDate": d, "Firm": f"D{i}", "Action": "down"})
    for i in range(init): rows.append({"GradeDate": d, "Firm": f"I{i}", "Action": "init"})
    return pd.DataFrame(rows)


def test_broad_consensus_improvement_is_candidate_and_strong():
    result = build_consensus_change(_summary(), _actions(up=2), {"mean": 120, "high": 150, "low": 90}, {"Pris": 100}, as_of="2026-09-09")
    assert result["Konsensusförändring kandidat"] is True
    assert result["Konsensusförändring stark"] is True
    assert result["Konsensus breadth förändring"] > 0.08
    assert result["Konsensus uppgraderingar 45d"] == 2
    assert round(result["Riktkurs dispersion"], 6) == 0.5


def test_single_analyst_action_never_qualifies_on_its_own():
    flat = _summary(current=(2, 4, 5, 0, 0), previous=(2, 4, 5, 0, 0))
    result = build_consensus_change(flat, _actions(up=1), None, {"Pris": 100}, as_of="2026-09-09")
    assert result["Konsensusförändring kandidat"] is False


def test_broad_downgrades_are_warning_and_veto_positive_candidate():
    result = build_consensus_change(
        _summary(current=(1, 2, 4, 3, 1), previous=(3, 5, 3, 0, 0)),
        _actions(up=0, down=3), None, {"Pris": 100}, as_of="2026-09-09"
    )
    assert result["Konsensusförändring varning"] is True
    assert result["Konsensusförändring kandidat"] is False
    assert "försämras" in result["Konsensusförändring status"].lower()


def test_new_coverage_is_context_not_buy_advantage():
    flat = _summary(current=(2, 4, 5, 0, 0), previous=(2, 4, 5, 0, 0))
    result = build_consensus_change(flat, _actions(init=2), None, {}, as_of="2026-09-09")
    assert result["Konsensusförändring kandidat"] is False
    assert result["Konsensusförändring status"] == "Bevakningen breddas"


def test_selector_is_deterministic_and_prefers_strong_breadth():
    df = pd.DataFrame([
        {"Ticker":"B.ST", "Konsensusförändring kandidat":True, "Konsensusförändring stark":False, "Konsensus breadth förändring":0.15, "Konsensus åtgärdsbalans 45d":1.0, "Konsensus uppgraderingar 45d":3, "Konsensus aktiva analyshus 45d":3},
        {"Ticker":"A.ST", "Konsensusförändring kandidat":True, "Konsensusförändring stark":True, "Konsensus breadth förändring":0.10, "Konsensus åtgärdsbalans 45d":1.0, "Konsensus uppgraderingar 45d":2, "Konsensus aktiva analyshus 45d":2},
    ])
    picked = select_consensus_change_candidates(df, quota=1)
    assert picked == [(1, "Konsensusförändring")]


def test_no_consensus_score_and_version_ui_ledger_wiring():
    root = Path(__file__).resolve().parents[1]
    engine = (root / "consensus_change_engine.py").read_text(encoding="utf-8")
    app = (root / "app.py").read_text(encoding="utf-8")
    ledger = (root / "recommendation_ledger.py").read_text(encoding="utf-8")
    finalist = (root / "finalist_selection.py").read_text(encoding="utf-8")
    assert "Konsensus Score" not in engine
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Analytikerkollektivet ändrar sig – Consensus Change" in app
    assert "Konsensus breadth förändring" in ledger
    assert 'reason_keys[idx] = "consensus_change"' in finalist


def test_target_dispersion_is_descriptive_not_claimed_as_change():
    result = build_consensus_change(_summary(), _actions(up=2), {"mean": 100, "high": 130, "low": 70}, {"Pris": 80}, as_of="2026-09-09")
    assert result["Riktkurs dispersion"] == 0.6
    assert "dispersion förändring" not in result
