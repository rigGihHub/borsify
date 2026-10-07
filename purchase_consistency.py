"""Shared final purchase policy. Missing verification never strengthens a decision."""
import math
import pandas as pd
from analysis_confidence import assess_analysis_confidence
from lifetime_suitability import lifetime_blockers

BUY_SIGNALS = {"KÖP NU", "KÖP", "KÖP / ÄG", "BYGG POSITION", "KÖP / ÄG LÅNGSIKTIGT", "BYGG LÅNGSIKTIGT"}

def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return math.nan

def purchase_blockers(row, horizon="year"):
    reasons = []
    confidence = assess_analysis_confidence(row)
    conviction = number(row.get("Deal Conviction Score"))
    if not math.isfinite(conviction) or conviction < 60:
        observed = f"{conviction:.0f}/100" if math.isfinite(conviction) else "saknas"
        reasons.append(f"köptesens stöd är {observed}; minst 60/100 krävs")
    if confidence["Analysis Confidence nivå"] < 3 or confidence["Analysis Confidence Score"] < 70:
        reasons.append("verifiera analysunderlaget: " + (confidence["Analysis Confidence blockerare"] or confidence["Analysis Confidence varningar"] or "analysförtroendet måste nå 70/100"))
    for field, label in [("Ingångsläge nivå", "ingångsläget"), ("Bolagsbedömning nivå", "bolagsbedömningen")]:
        if str(row.get(field, "")).lower() in {"red", "orange"}:
            reasons.append(f"{label} måste förbättras före köp")
    if row.get("För långt gången") is True or str(row.get("För långt gången")).lower() == "true":
        reasons.append("kursen är översträckt; invänta bättre ingång och en ny priskontroll")
    if str(row.get("Value Trap verdict", "")) == "VALUE_TRAP":
        reasons.append("värdefällerisk måste undanröjas")
    if horizon == "lifetime":
        reasons.extend(lifetime_blockers(row))
        years = number(row.get("Historik år"))
        if not math.isfinite(years) or years < 3:
            reasons.append("minst tre års jämförbar lönsamhets- och kassaflödeshistorik krävs")
        if number(row.get("Deep Confidence")) < 70 or not math.isfinite(number(row.get("Deep Confidence"))):
            reasons.append("långsiktigt ägande kräver minst 70/100 i fördjupad flerårsanalys")
        if number(row.get("KPI strukturerad täckning")) < 3 or not math.isfinite(number(row.get("KPI strukturerad täckning"))):
            reasons.append("verifiera minst tre relevanta verksamhetsmått och deras uthållighet")
        report = pd.to_datetime(row.get("Rapportdatum"), errors="coerce", utc=True)
        if pd.isna(report) or (pd.Timestamp.now(tz="UTC") - report).days > 180 or report > pd.Timestamp.now(tz="UTC"):
            reasons.append("en daterad rapport från senaste halvåret krävs för långsiktigt köp")
    return list(dict.fromkeys(reasons))

def reconcile_purchase_decisions(frame, horizon):
    out = frame.copy()
    for index, row in out.iterrows():
        blockers = purchase_blockers(row, horizon)
        out.at[index, "Köpbeslut hinder"] = "; ".join(blockers)
        if blockers:
            out.at[index, "Signal"] = "BEVAKA"
            out.at[index, "Signal kort"] = "Invänta verifiering eller bättre läge"
            out.at[index, "Signal förklaring"] = "; ".join(blockers)
    return out
