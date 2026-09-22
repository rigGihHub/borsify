from quality_compounder_ignored import assess_quality_compounder_ignored


def test_strong_ignored_compounder_long_horizon():
    r=assess_quality_compounder_ignored({
        "Kvalitet":82,"Risk":74,"ROE":.21,"Vinstmarginal":.17,"FCF yield":.045,
        "Skuld/eget kapital":.45,"INVEST Score":79,"Värdering":63,
        "1 mån":.01,"3 mån":.04,"Avstånd SMA200":.03,"12–1 momentum":.08,
        "Förändringsbekräftelse negativa familjer":"","Report Delta positiva":2,"Report Delta negativa":0,
    },"lifetime")
    assert r["Ignored compounder nivå"] == 3
    assert "Quality compounder" in r["Ignored compounder"]


def test_weak_price_plus_fundamental_deterioration_is_not_a_bargain():
    r=assess_quality_compounder_ignored({
        "Kvalitet":80,"Risk":70,"ROE":.18,"Vinstmarginal":.13,"FCF yield":.03,
        "1 mån":-.08,"3 mån":-.12,
        "Förändringsbekräftelse negativa familjer":"rapport, konsensus",
        "Report Delta positiva":0,"Report Delta negativa":3,
    },"long")
    assert r["Ignored compounder nivå"] == -1


def test_compounder_signal_does_not_affect_short_horizon():
    r=assess_quality_compounder_ignored({
        "Kvalitet":90,"Risk":80,"ROE":.25,"Vinstmarginal":.20,"FCF yield":.05,
        "1 mån":0,"3 mån":0,"Avstånd SMA200":0,
    },"medium")
    assert r["Ignored compounder nivå"] == 0
    assert "bara långsiktigt" in r["Ignored compounder"]


def test_not_ignored_if_stock_already_running():
    r=assess_quality_compounder_ignored({
        "Kvalitet":85,"Risk":75,"ROE":.22,"Vinstmarginal":.18,"FCF yield":.04,
        "INVEST Score":80,"1 mån":.18,"3 mån":.31,"Avstånd SMA200":.20,
    },"lifetime")
    assert r["Ignored compounder nivå"] <= 1


def test_app_and_ranking_wired():
    app=open("app.py",encoding="utf-8").read()
    rank=open("horizon_rankings.py",encoding="utf-8").read()
    ledger=open("recommendation_ledger.py",encoding="utf-8").read()
    assert 'APP_VERSION = "4.39.2"' in app
    assert "Ignored compounder" in app
    assert "add_quality_compounder_ignored(ranked, horizon)" in app
    assert "add_quality_compounder_ignored(out,horizon)" in rank.replace(" ", "")
    assert '"Deal Conviction Score"' in rank
    assert '"Ignored compounder förklaring"' in ledger
