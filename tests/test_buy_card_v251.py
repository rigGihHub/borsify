from buy_card import build_buy_card

def base_row():
    return {
        "Kvalitet":82,
        "Risk":78,
        "Värdering":72,
        "INVEST Score":76,
        "1 mån":.12,
        "3 mån":.24,
        "Volymkvot":1.5,
        "RSI14":62,
        "ROE":.22,
        "Vinstmarginal":.16,
        "Datatäckning":.90,
        "Riskflaggor":"—",
    }

def test_every_horizon_answers_four_decision_questions():
    for horizon in ("day","medium","long","lifetime"):
        card=build_buy_card(base_row(),horizon)
        assert set(card)=={
            "Varför köpa",
            "Varför nu",
            "Största risk",
            "Vad skulle få Borsify att ändra sig",
        }
        assert all(str(v).strip() for v in card.values())

def test_risk_flags_are_not_hidden():
    row=base_row()
    row["Riskflaggor"]="hög skuldsättning, fallande lång trend"
    card=build_buy_card(row,"long")
    assert "skuldsättning" in card["Största risk"].lower()

def test_missing_data_is_described_cautiously():
    row=base_row()
    row["Riskflaggor"]="—"
    row["Datatäckning"]=.55
    card=build_buy_card(row,"long")
    assert "inte komplett" in card["Största risk"].lower()

def test_lifetime_card_uses_plain_language():
    card=build_buy_card(base_row(),"lifetime")
    text=" ".join(card.values()).lower()
    assert "alpha" not in text
    assert "proxy" not in text
    assert "oos" not in text
