from prefilter_history import save_prefilter_validation, get_prefilter_validation_history

def test_prefilter_history_roundtrip(tmp_path):
    db=tmp_path/"history.db"
    result={
        "universe":100,"pool":60,"targets":10,"retained":10,
        "retention":1.0,"fraction":.60,"missed":[]
    }
    save_prefilter_validation(db,"Sverige",result,"2.64.0",validation_date="2026-09-03")
    hist=get_prefilter_validation_history(db,market="Sverige")
    assert len(hist)==1
    assert float(hist.iloc[0]["retention"])==1.0
    assert int(hist.iloc[0]["pool_size"])==60
