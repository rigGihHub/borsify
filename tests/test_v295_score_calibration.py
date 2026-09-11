import pandas as pd

from score_calibration import (
    prepare_score_calibration_data,
    score_calibration_table,
    score_calibration_summary,
    MIN_CALIBRATION_CASES,
)


def _rows(kind="short", n_per_band=8, worsening=False):
    recs=[]; outs=[]
    bands=[55,65,75,85]
    for bi,score in enumerate(bands):
        for i in range(n_per_band):
            rid=f"{kind}-{bi}-{i}"
            # Space same-symbol repeats far enough apart only by using unique symbols.
            recs.append({
                "record_id":rid,"symbol":f"S{bi}{i}.ST","captured_date":f"2026-01-{(i%20)+1:02d}",
                "horizon_type":kind,"score":score,"gate":"x","model_version":"2.95.0"
            })
            base=(3-bi if worsening else bi)*0.05
            outs.append({"record_id":rid,"horizon":"1m" if kind=="short" else "1y","return_pct":base + i*0.0001})
    return pd.DataFrame(recs),pd.DataFrame(outs)


def test_calibration_has_fixed_score_bands_and_independent_cases():
    recs,outs=_rows(n_per_band=8)
    t=score_calibration_table(recs,outs,"1m")
    assert t["Scoregrupp"].tolist()==["Under 60","60–69","70–79","80+"]
    assert t["Oberoende case"].sum()==32
    assert t["Typ"].unique().tolist()==["Kortsiktig"]


def test_calibration_detects_monotonic_improvement():
    recs,outs=_rows(n_per_band=8)
    s=score_calibration_summary(recs,outs,"1m")
    assert s["status"]=="Bra ordning"


def test_calibration_flags_reversed_scores():
    recs,outs=_rows(n_per_band=8,worsening=True)
    s=score_calibration_summary(recs,outs,"1m")
    assert s["status"]=="Kalibreringen bör granskas"


def test_calibration_waits_for_enough_cases():
    recs,outs=_rows(n_per_band=4)
    s=score_calibration_summary(recs,outs,"1m")
    assert s["status"]=="För lite underlag"


def test_shared_6m_horizon_never_mixes_short_and_long_scores():
    rs=[]; os=[]
    for kind in ["short","long"]:
        for i in range(8):
            rid=f"{kind}-{i}"
            rs.append({"record_id":rid,"symbol":f"{kind}{i}","captured_date":f"2026-01-{i+1:02d}","horizon_type":kind,"score":65 if kind=="short" else 85})
            os.append({"record_id":rid,"horizon":"6m","return_pct":0.1 if kind=="short" else 0.2})
    t=score_calibration_table(pd.DataFrame(rs),pd.DataFrame(os),"6m")
    assert set(t["Typ"])=={"Kortsiktig","Långsiktig"}
    assert len(t)==2


def test_v295_ui_exposes_calibration_without_auto_reweighting():
    app=open("app.py",encoding="utf-8").read()
    assert 'APP_VERSION = "3.81.0"' in app
    assert "Betyder högre Borsify-betyg faktiskt bättre utfall?" in app
    assert "leder aldrig till automatisk viktändring" in app
