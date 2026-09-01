import pandas as pd


def _merge_records(pool: pd.DataFrame, records: dict) -> pd.DataFrame:
    if records:
        assessment_frame = pd.DataFrame.from_dict(records, orient="index")
        for key in assessment_frame.columns:
            assessment_frame[key] = assessment_frame[key].astype("object")
        existing = [c for c in assessment_frame.columns if c in pool.columns]
        if existing:
            pool = pool.drop(columns=existing)
        pool = pool.join(assessment_frame, how="left")
    return pool


def test_list_values_join_as_single_cells():
    pool = pd.DataFrame({"Ticker": ["A", "B"]}, index=[10, 20])
    records = {10: {"Case Supports": ["quality", "catalyst"]}}
    out = _merge_records(pool, records)
    assert out.at[10, "Case Supports"] == ["quality", "catalyst"]
    assert pd.isna(out.at[20, "Case Supports"])

def test_dict_values_join_as_single_cells():
    pool = pd.DataFrame({"Ticker": ["A"]}, index=[7])
    records = {7: {"Scenario detail": {"bear": -0.2, "bull": 0.4}}}
    out = _merge_records(pool, records)
    assert out.at[7, "Scenario detail"]["bull"] == 0.4

def test_existing_columns_are_replaced_cleanly():
    pool = pd.DataFrame({"Ticker": ["A"], "Score": [1.0]}, index=[1])
    records = {1: {"Score": 77.5, "Warnings": ["risk 1"], "Meta": {"source": "x"}}}
    out = _merge_records(pool, records)
    assert out.at[1, "Score"] == 77.5
    assert out.at[1, "Warnings"] == ["risk 1"]
    assert out.at[1, "Meta"] == {"source": "x"}
