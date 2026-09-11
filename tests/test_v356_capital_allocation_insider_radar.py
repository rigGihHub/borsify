from pathlib import Path

import numpy as np
import pandas as pd

from capital_allocation_insider_radar import (
    analyze_insider_cluster,
    build_capital_allocation_insider_radar,
    build_capital_allocation_metrics,
    select_owner_signal_candidates,
)

ROOT = Path(__file__).resolve().parents[1]


def _cashflow(repurchase=-150.0, issuance=10.0, dividends=-20.0):
    cols = [pd.Timestamp("2026-06-30"), pd.Timestamp("2025-06-30")]
    return pd.DataFrame(
        {
            cols[0]: [repurchase, issuance, dividends],
            cols[1]: [-50.0, 5.0, -18.0],
        },
        index=["Repurchase Of Capital Stock", "Issuance Of Capital Stock", "Cash Dividends Paid"],
    )


def _balance(latest_debt=400.0, prior_debt=600.0, latest_cash=100.0, prior_cash=100.0):
    cols = [pd.Timestamp("2026-06-30"), pd.Timestamp("2025-06-30")]
    return pd.DataFrame(
        {
            cols[0]: [latest_debt, latest_cash],
            cols[1]: [prior_debt, prior_cash],
        },
        index=["Total Debt", "Cash And Cash Equivalents"],
    )


def _insiders():
    return pd.DataFrame(
        {
            "Start Date": ["2026-08-20", "2026-08-10", "2026-08-05", "2026-08-01"],
            "Insider": ["Alice", "Bob", "Cara", "Dan"],
            "Transaction": ["Purchase", "Open Market Purchase", "Sale", "Stock Award"],
            "Value": [300_000, 250_000, 100_000, 500_000],
        }
    )


def test_net_buybacks_are_measured_after_issuance_and_relative_to_market_cap():
    metrics = build_capital_allocation_metrics(
        _cashflow(), _balance(), {"market_cap": 10_000.0}
    )
    assert metrics["Kapitalallokering nettoåterköp"] == 140.0
    assert np.isclose(metrics["Kapitalallokering återköpsyield"], 0.014)
    assert metrics["Kapitalallokering skuldtrend"] < -0.3


def test_insider_cluster_requires_independent_open_market_buyers_and_ignores_awards():
    out = analyze_insider_cluster(_insiders(), as_of="2026-09-09", lookback_days=120)
    assert out["Insider köp antal"] == 2
    assert out["Insider köpare antal"] == 2
    assert out["Insider sälj antal"] == 1
    assert out["Insider kluster"] is True
    assert out["Insider starkt kluster"] is False
    assert out["Insider köp värde"] == 550_000


def test_owner_signal_can_open_discovery_door_without_new_score():
    out = build_capital_allocation_insider_radar(
        _cashflow(), _balance(), _insiders(),
        {"market_cap": 10_000.0, "Värdering": 60, "Skuld/eget kapital": 80, "Sektor": "Industrials"},
        as_of="2026-09-09",
    )
    assert out["Ägarsignal kandidat"] is True
    assert out["Ägarsignal stark"] is True
    assert "score" not in " ".join(out.keys()).lower()
    assert out["Insider kluster"] is True


def test_heavy_dilution_blocks_positive_owner_signal():
    out = build_capital_allocation_insider_radar(
        _cashflow(repurchase=-10.0, issuance=500.0), _balance(), _insiders(),
        {"market_cap": 10_000.0, "Värdering": 70, "Skuld/eget kapital": 80, "Sektor": "Industrials"},
        as_of="2026-09-09",
    )
    assert out["Ägarsignal kandidat"] is False
    assert out["Ägarsignal status"] == "Ägarutspädning väger tyngre"


def test_selector_is_deterministic_and_prefers_stronger_cluster():
    df = pd.DataFrame(
        {
            "Ticker": ["BBB.ST", "AAA.ST", "CCC.ST"],
            "Ägarsignal kandidat": [True, True, True],
            "Ägarsignal stark": [False, True, True],
            "Insider kluster": [True, True, False],
            "Insider köpare antal": [2, 3, 0],
            "Kapitalallokering återköpsyield": [0.03, 0.01, 0.05],
            "Kapitalallokering skuldtrend": [-0.2, -0.1, -0.3],
        },
        index=[11, 12, 13],
    )
    assert select_owner_signal_candidates(df, quota=1) == [(12, "Ägarsignal")]


def test_version_wiring_and_pit_freeze_are_present():
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    finalist = (ROOT / "finalist_selection.py").read_text(encoding="utf-8")
    ledger = (ROOT / "recommendation_ledger.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.81.0"' in app
    assert "build_capital_allocation_insider_radar" in app
    assert 'st.session_state["bq_owner_signal_radar"]' in app
    assert "select_owner_signal_candidates" in finalist
    assert 'reason_keys[idx] = "owner_signal"' in finalist
    assert '"Ägarsignal status"' in ledger
    assert '"Insider kluster"' in ledger
