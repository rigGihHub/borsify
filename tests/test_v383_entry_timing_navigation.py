import pandas as pd
from entry_timing import assess_entry_timing, add_entry_timing


def test_chasing_risk_flags_fast_run_medium():
    row={"Dagsförändring":.03,"1 mån":.34,"3 mån":.58,"Avstånd SMA200":.27,"RSI14":81}
    r=assess_entry_timing(row,"medium")
    assert r["Ingångsläge nivå"] == "red"
    assert r["Chasing-risk"] is True
    assert "Jaga inte" in r["Ingångsläge"]


def test_strong_but_not_extreme_can_remain_buyable():
    row={"Dagsförändring":.01,"1 mån":.09,"3 mån":.18,"Avstånd SMA200":.10,"RSI14":66}
    r=assess_entry_timing(row,"medium")
    assert r["Ingångsläge nivå"] in {"green","yellow"}
    assert r["Chasing-risk"] is False


def test_long_horizon_is_more_tolerant_but_not_blind():
    warm={"1 mån":.22,"3 mån":.40,"Avstånd SMA200":.19,"RSI14":76}
    extreme={"1 mån":.45,"3 mån":.75,"Avstånd SMA200":.32,"RSI14":86}
    assert assess_entry_timing(warm,"lifetime")["Ingångsläge nivå"] != "red"
    assert assess_entry_timing(extreme,"lifetime")["Ingångsläge nivå"] == "red"


def test_add_entry_timing_keeps_rows():
    df=pd.DataFrame([{"Ticker":"A","1 mån":.1},{"Ticker":"B","1 mån":.4,"Avstånd SMA200":.3}])
    out=add_entry_timing(df,"year")
    assert list(out["Ticker"]) == ["A","B"]
    assert "Ingångsläge" in out.columns


def test_ui_has_direct_horizon_buttons_clickable_stocks_ai_and_version():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert "⚡ Köp nu · sälj snart" in app
    assert "📈 Köp nu · behåll 1 år" in app
    assert "♾️ Köp för resten av livet" in app
    assert 'st.session_state["bq_open_stock_ticker"]' in app
    assert "render_case_ai_qa(row, horizon, rank)" in app
    assert "Ingångsläge" in app
