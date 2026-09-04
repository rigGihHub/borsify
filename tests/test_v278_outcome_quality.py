import pandas as pd
import pytest

from recommendation_ledger import evaluate_record_from_history, outcome_summary


def _record():
    return {
        "record_id":"r1", "symbol":"ABC", "captured_date":"2026-01-02",
        "entry_price":100.0, "horizon_type":"short",
    }


def test_outcome_tracks_benchmark_excess_and_path_quality():
    idx=pd.bdate_range("2026-01-02", periods=70)
    stock=pd.DataFrame({"Close":[100+i for i in range(70)]}, index=idx)
    bench=pd.DataFrame({"Close":[200+i*0.5 for i in range(70)]}, index=idx)
    rows=evaluate_record_from_history(
        _record(), stock, as_of=idx[-1], benchmark_history=bench,
        benchmark_symbol="^TEST", benchmark_name="Testindex",
    )
    one=next(r for r in rows if r["horizon"]=="1m")
    assert one["return_pct"] == pytest.approx(0.21)
    assert one["benchmark_return_pct"] == pytest.approx((210.5/200)-1)
    assert one["excess_return_pct"] == pytest.approx(one["return_pct"]-one["benchmark_return_pct"])
    assert one["beat_benchmark"] is True
    assert one["best_return_pct"] == pytest.approx(0.21)
    assert one["worst_return_pct"] == pytest.approx(0.0)
    assert one["sessions_to_best"] == 21


def test_benchmark_calendar_can_differ_from_stock_calendar():
    idx=pd.bdate_range("2026-01-02", periods=30)
    stock=pd.DataFrame({"Close":[100]*30}, index=idx)
    bench_idx=idx.delete([3,8,13])
    bench=pd.DataFrame({"Close":[200+i for i in range(len(bench_idx))]}, index=bench_idx)
    rows=evaluate_record_from_history(_record(), stock, as_of=idx[-1], benchmark_history=bench)
    one=next(r for r in rows if r["horizon"]=="1m")
    assert one["benchmark_return_pct"] is not None


def test_missing_benchmark_never_invents_excess_return():
    idx=pd.bdate_range("2026-01-02", periods=30)
    stock=pd.DataFrame({"Close":[100]*30}, index=idx)
    rows=evaluate_record_from_history(_record(), stock, as_of=idx[-1])
    one=next(r for r in rows if r["horizon"]=="1m")
    assert one["benchmark_return_pct"] is None
    assert one["excess_return_pct"] is None
    assert one["beat_benchmark"] is None


def test_outcome_summary_prefers_relative_metrics_when_available():
    recs=pd.DataFrame([{"record_id":"r1","horizon_type":"short","gate":"KÖP","score":80,"confidence":75,"model_version":"x"}])
    outs=pd.DataFrame([{"record_id":"r1","return_pct":0.10,"excess_return_pct":0.04,"sessions_to_best":12}])
    result=outcome_summary(recs,outs)
    assert result["benchmark_evaluated"] == 1
    assert result["median_excess_return"] == pytest.approx(0.04)
    assert result["beat_benchmark_rate"] == pytest.approx(1.0)
    assert result["median_sessions_to_best"] == pytest.approx(12)


def test_learning_uses_relative_only_when_complete():
    from recommendation_learning import learning_tables
    recs=[]; outs=[]
    for i in range(16):
        high=i>=8
        recs.append({"record_id":f"x{i}","symbol":f"X{i}","name":"X","horizon_type":"short",
                     "gate":"A" if high else "B","score":80 if high else 60,"confidence":80,
                     "model_version":"2.78.0","profile":"Balanserad","market":"Sverige","rank":1,
                     "captured_date":"2026-01-01","snapshot_json":"{}"})
        # Raw return says high is better, excess says high is worse. Complete relative
        # coverage must therefore flip the cohort conclusion.
        outs.append({"record_id":f"x{i}","horizon":"1m","return_pct":0.10 if high else 0.01,
                     "excess_return_pct":-0.02 if high else 0.03})
    table=learning_tables(pd.DataFrame(recs),pd.DataFrame(outs),"1m")["Bedömning"]
    med=dict(zip(table["Grupp"],table["Median"]))
    assert med["B"] > med["A"]
    assert set(table["Mätning"]) == {"Mot index"}


def test_learning_does_not_mix_raw_and_relative_outcomes():
    from recommendation_learning import learning_tables
    recs=[]; outs=[]
    for i in range(16):
        recs.append({"record_id":f"m{i}","symbol":f"M{i}","name":"M","horizon_type":"short",
                     "gate":"A" if i>=8 else "B","score":80 if i>=8 else 60,"confidence":80,
                     "model_version":"2.78.0","profile":"Balanserad","market":"Sverige","rank":1,
                     "captured_date":"2026-01-01","snapshot_json":"{}"})
        outs.append({"record_id":f"m{i}","horizon":"1m","return_pct":0.10 if i>=8 else 0.01,
                     "excess_return_pct":None if i==0 else (-0.02 if i>=8 else 0.03)})
    table=learning_tables(pd.DataFrame(recs),pd.DataFrame(outs),"1m")["Bedömning"]
    med=dict(zip(table["Grupp"],table["Median"]))
    assert med["A"] > med["B"]
    assert set(table["Mätning"]) == {"Rå kursutveckling"}
