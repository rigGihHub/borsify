"""Convert vendor percentages once, retaining provenance and rejecting ambiguity."""
import math

def num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan

def dividend_fields(info):
    rate, price = num(info.get("dividendRate")), num(info.get("currentPrice", info.get("regularMarketPrice")))
    raw = num(info.get("dividendYield"))
    if math.isfinite(rate) and rate >= 0 and math.isfinite(price) and price > 0:
        value, source = rate / price, "Årlig utdelning / aktuell kurs (Yahoo)"
    else:
        value, source = raw / 100, "Yahoo dividendYield: procent omräknat till andel"
    if not math.isfinite(value) or not 0 <= value <= 1:
        value, source = math.nan, "Utdelningsuppgift saknas eller kräver verifiering"
    return {"Direktavkastning": value, "Direktavkastning källa": source, "Utdelningsenhet version": 1}

def clean_legacy_dividend(payload):
    out = dict(payload)
    if out.get("Utdelningsenhet version") != 1:
        out["Direktavkastning"] = math.nan
        out["Direktavkastning källa"] = "Äldre uppgift med okänd enhet; hämta ny bolagsdata"
    return out
