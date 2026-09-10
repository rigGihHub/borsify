import sqlite3
from pathlib import Path

from report_delta_memory import (
    compare_report_delta_memory, ensure_report_delta_memory_table,
    previous_report_snapshot, save_report_snapshot, snapshot_from_report_delta,
)


def _metrics(rev_acc=.02, margin=.01, fcf=.10, earnings=.08, estimate=.01):
    return {
        "Senaste EPS-överraskning": .05,
        "Omsättning YoY senaste kvartal": .10,
        "Omsättning acceleration": rev_acc,
        "Marginal YoY förändring": margin,
        "FCF YoY senaste kvartal": fcf,
        "Vinst YoY senaste kvartal": earnings,
        "EPS-estimat förändring": estimate,
        "EPS-revisionsbalans": .20,
    }


def _report(date, positives=2, negatives=0):
    return {"Post-report datum": date}, {
        "Report Delta evidens": 6, "Report Delta positiva": positives,
        "Report Delta negativa": negatives, "Report Delta kandidat": positives >= 3,
        "Report Delta underreaktion": False, "Report Delta status": "test",
    }


def test_first_observed_report_has_no_reconstructed_history():
    post, rd = _report("2026-09-01")
    snap = snapshot_from_report_delta("ABC.ST", _metrics(), post, rd, "2026-09-09")
    out = compare_report_delta_memory(snap, None)
    assert out["Rapportminne status"] == "För lite rapporthistorik"
    assert out["Rapportminne historik"] is False


def test_same_report_is_stored_once_even_when_scanner_runs_again():
    conn = sqlite3.connect(":memory:")
    ensure_report_delta_memory_table(conn)
    post, rd = _report("2026-09-01")
    snap = snapshot_from_report_delta("ABC.ST", _metrics(), post, rd, "2026-09-09")
    save_report_snapshot(conn, snap)
    save_report_snapshot(conn, snap)
    assert conn.execute("select count(*) from report_delta_snapshots").fetchone()[0] == 1


def test_previous_snapshot_means_previous_report_not_previous_scan_day():
    conn = sqlite3.connect(":memory:")
    for d in ["2026-05-01", "2026-08-01"]:
        post, rd = _report(d)
        save_report_snapshot(conn, snapshot_from_report_delta("ABC.ST", _metrics(), post, rd, "2026-09-09"))
    prev = previous_report_snapshot(conn, "ABC.ST", "2026-09-01")
    assert prev["report_date"] == "2026-08-01"


def test_detects_broad_improvement_between_real_reports():
    p1, r1 = _report("2026-05-01", positives=1, negatives=1)
    p2, r2 = _report("2026-08-01", positives=4, negatives=0)
    prev = snapshot_from_report_delta("ABC.ST", _metrics(rev_acc=.00, margin=.00, fcf=.05, earnings=.02, estimate=.00), p1, r1, "2026-05-02")
    cur = snapshot_from_report_delta("ABC.ST", _metrics(rev_acc=.05, margin=.02, fcf=.25, earnings=.15, estimate=.03), p2, r2, "2026-08-02")
    out = compare_report_delta_memory(cur, prev)
    assert out["Rapportminne status"] == "Rapportförändringen förbättras"
    assert out["Rapportminne förbättring"] is True


def test_missing_verified_report_date_creates_no_snapshot():
    snap = snapshot_from_report_delta("ABC.ST", _metrics(), {"Post-report datum": "—"}, {}, "2026-09-09")
    assert snap is None


def test_release_wiring():
    root = Path(__file__).resolve().parents[1]
    app = (root / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "3.73.0"' in app
    assert "compare_report_delta_memory" in app
    assert "Rapportminne status" in app
