"""Expectation Gap context layer.

Compares independently observed *change strength* with the market expectation level
we can actually observe. This is deliberately categorical, not a score, and never
invents a market-expectation gap when analyst/target data is too thin.
"""
from __future__ import annotations
from typing import Any
import math


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else float("nan")
    except Exception:
        return float("nan")


def _yes(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in {"1", "true", "ja", "yes"}


def build_expectation_gap(record: dict[str, Any] | None) -> dict[str, Any]:
    r = record or {}
    positive = int(_num(r.get("Förändringsbekräftelse positiva familjer antal")) if math.isfinite(_num(r.get("Förändringsbekräftelse positiva familjer antal"))) else 0)
    # Backwards-compatible derivation from the family string used by v3.68+.
    if positive == 0:
        positive = len([x for x in str(r.get("Förändringsbekräftelse positiva familjer") or "").split(",") if x.strip()])
    negative = len([x for x in str(r.get("Förändringsbekräftelse negativa familjer") or "").split(",") if x.strip()])
    confirmed = _yes(r.get("Förändringsbekräftelse kandidat")) and positive >= 2 and negative == 0
    strong_change = confirmed and (positive >= 3 or _yes(r.get("Förändringsbekräftelse stark")))

    bull = _num(r.get("Konsensus bullish andel"))
    analysts = _num(r.get("Konsensus analytiker antal"))
    upside = _num(r.get("Riktkurs potential"))
    crowded = _yes(r.get("Crowded varning"))
    crowded_strong = _yes(r.get("Crowded stark varning"))

    broad_expectations = math.isfinite(analysts) and analysts >= 5 and math.isfinite(bull)
    target_known = math.isfinite(upside)

    if not confirmed:
        status = "Ingen verifierad positiv förändring att jämföra"
        favorable = False
        warning = bool(negative)
        why = "Expectation Gap aktiveras först när minst två oberoende PIT-familjer bekräftar en positiv förändring."
    elif not broad_expectations:
        status = "För lite förväntningsdata"
        favorable = False
        warning = False
        why = "Förändringen är bekräftad, men Borsify har inte tillräckligt bred analytikerkonsensus för att påstå hur höga marknadens förväntningar är."
    elif crowded_strong:
        status = "Stark förändring – men mycket höga förväntningar"
        favorable = False
        warning = True
        why = "Den underliggande förändringen är stark, men analytikerkonsensus och kvarvarande uppsida/värdering tyder på att mycket redan kan vara inprisat."
    elif crowded:
        status = "Förändring bekräftad – men förväntningarna är höga"
        favorable = False
        warning = True
        why = "Flera oberoende förändringar förbättras, men den positiva konsensusbilden är redan trång. Borsify behandlar det som förväntningsrisk, inte som ett köpförbud."
    elif target_known and upside >= 0.15 and bull < 0.80:
        status = "Förbättring före förväntningarna"
        favorable = True
        warning = False
        strength = "stark " if strong_change else ""
        why = f"En {strength}bekräftad förändring finns samtidigt som konsensus ännu inte är extremt positiv och observerad riktkurspotential fortfarande är minst cirka 15 %."
    elif target_known and upside <= 0.05:
        status = "Förändringen är starkare än förr – men uppsidan ser redan liten ut"
        favorable = False
        warning = True
        why = "Förändringen är positivt bekräftad, men den observerade riktkurspotentialen är högst cirka 5 %. Det minskar stödet för att marknaden ligger tydligt efter."
    else:
        status = "Positiv förändring – inget tydligt expectation gap"
        favorable = False
        warning = False
        why = "Förändringen är bekräftad, men tillgänglig konsensus- och riktkursdata räcker inte för att säga att förväntningarna tydligt ligger efter förbättringen."

    return {
        "Expectation Gap status": status,
        "Expectation Gap kandidat": favorable,
        "Expectation Gap stark": bool(favorable and strong_change),
        "Expectation Gap varning": warning,
        "Expectation Gap förändringsfamiljer": positive,
        "Expectation Gap bullish andel": bull,
        "Expectation Gap analytiker antal": analysts,
        "Expectation Gap riktkurs potential": upside,
        "Expectation Gap förklaring": why,
    }
