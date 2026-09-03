from datetime import datetime, timedelta, timezone

from fundamental_cache import get_cached_fundamentals, put_cached_fundamentals


def test_persistent_cache_roundtrip(tmp_path):
    db=tmp_path/"cache.db"
    now=datetime(2026,9,3,10,0,tzinfo=timezone.utc)
    payload={"Namn":"Test AB","P/E":15.0,"ROE":None}
    put_cached_fundamentals(db,"TEST.ST",payload,now=now)
    out=get_cached_fundamentals(db,"TEST.ST",max_age_hours=24,now=now+timedelta(hours=12))
    assert out["Namn"]=="Test AB"
    assert out["P/E"]==15.0
    assert out["ROE"] is None

def test_persistent_cache_expires(tmp_path):
    db=tmp_path/"cache.db"
    now=datetime(2026,9,3,10,0,tzinfo=timezone.utc)
    put_cached_fundamentals(db,"TEST.ST",{"Namn":"Test AB"},now=now)
    out=get_cached_fundamentals(db,"TEST.ST",max_age_hours=24,now=now+timedelta(hours=25))
    assert out is None
