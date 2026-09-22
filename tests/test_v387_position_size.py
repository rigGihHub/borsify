from position_entry_guidance import assess_position_entry


def test_full_size_requires_green_axes_and_robust_risk():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"green","Risk":75})
    assert r["Första positionsstorlek %"] == 100


def test_green_axes_but_moderate_risk_caps_initial_size():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"green","Risk":60})
    assert r["Första positionsstorlek %"] == 50


def test_orange_entry_is_small_start_only():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"orange","Risk":80})
    assert r["Första positionsstorlek %"] == 25


def test_red_entry_is_zero_new_position():
    r=assess_position_entry({"Bolagsbedömning nivå":"green","Ingångsläge nivå":"red","Risk":90})
    assert r["Första positionsstorlek %"] == 0


def test_yellow_company_never_gets_full_initial_size():
    r=assess_position_entry({"Bolagsbedömning nivå":"yellow","Ingångsläge nivå":"green","Risk":90})
    assert r["Första positionsstorlek %"] == 50


def test_app_exposes_size_and_version():
    app=open('app.py',encoding='utf-8').read()
    assert 'APP_VERSION = "4.39.1"' in app
    assert '"Första positionsstorlek"' in app
    assert 'Första storlek' in app
    assert 'andel av din egen tänkta maxposition' in app
