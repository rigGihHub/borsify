import pandas as pd

from data_trust import assess_data_trust
from universe_quality import assess_universe_quality

def fresh_row():
    idx=pd.date_range(end=pd.Timestamp.today().normalize(),periods=120,freq="B")
    return {
        "Ticker":"TEST.ST","Namn":"Test AB","Pris":100.0,
        "Prisdatum":pd.Timestamp.today().date().isoformat(),
        "Valuta":"SEK","Universe QC":"VERIFIERAD","Datatäckning":.8,
        "Fundamental hämtad":pd.Timestamp.now().isoformat(),
        "P/E":15,"Forward P/E":14,"ROE":.18,"Vinstmarginal":.12,
        "Börsvärde BSEK":25,"_history":pd.DataFrame({"Close":range(120)},index=idx),
    }

def test_fresh_verified_data_gets_good_trust_status():
    result=assess_data_trust(fresh_row())
    assert result["Data Trust status"]=="GOTT UNDERLAG"
    assert result["Data Trust källa"]=="Yahoo Finance via yfinance"

def test_old_price_date_is_a_trust_stop():
    row=fresh_row()
    row["Prisdatum"]=(pd.Timestamp.today()-pd.Timedelta(days=10)).date().isoformat()
    result=assess_data_trust(row)
    assert result["Data Trust status"]=="STOPP"
    assert "gammal" in result["Data Trust stopp"]

def test_universe_qc_hard_excludes_old_price_date():
    row=fresh_row()
    row["Prisdatum"]=(pd.Timestamp.today()-pd.Timedelta(days=10)).date().isoformat()
    result=assess_universe_quality(row)
    assert result["Universe QC"]=="EXKLUDERA"
    assert "för gammalt" in result["Universe QC Problem"]

def test_broad_scan_does_not_pretend_report_date_is_known():
    result=assess_data_trust(fresh_row())
    assert "inte verifierat" in result["Data Trust rapportstatus"]

def test_deep_case_can_show_verified_report_date():
    row=fresh_row()
    row["Rapportdatum"]="2026-06-30"
    result=assess_data_trust(row)
    assert result["Data Trust rapportstatus"]=="Rapportdatum: 2026-06-30"
