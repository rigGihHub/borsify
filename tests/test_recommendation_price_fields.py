import pandas as pd
from recommendation_ledger import build_recommendation_records


def test_short_snapshot_keeps_price():
    df = pd.DataFrame([{
        "Ticker":"A.ST","Namn":"A","Pris":123.4,
        "Short Alpha Score":75,"Short Alpha Gate":"Starkt kortsiktigt case",
        "Short Alpha Confidence":70,"Short Confirmation Count":4,
    }])
    rows = build_recommendation_records(df,"short","2.36.1","Balanserad","Sverige")
    assert rows[0]["entry_price"] == 123.4


def test_long_snapshot_keeps_price():
    df = pd.DataFrame([{
        "Ticker":"B.ST","Namn":"B","Pris":88.8,
        "INVEST Score":82,"Case Gate":"Starkt case","Case Confidence":72,
    }])
    rows = build_recommendation_records(df,"long","2.36.1","Balanserad","Sverige")
    assert rows[0]["entry_price"] == 88.8
