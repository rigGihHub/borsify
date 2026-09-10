from __future__ import annotations

"""Plain-language decision layer for independently confirmed PIT changes.

This module creates no score and cannot make a stock buyable. It only translates
Change Confirmation into a concise, auditable "why now" statement.
"""

from typing import Any

_FAMILY_POSITIVE = {
    "Rapport": "rapportutvecklingen förbättras",
    "Konsensus": "analytikerna blir mer positiva",
    "Ledning": "ledningssignalerna stärks",
}
_FAMILY_NEGATIVE = {
    "Rapport": "rapportutvecklingen försämras",
    "Konsensus": "analytikerna blir mer negativa",
    "Ledning": "ledningssignalerna försvagas",
}


def _yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "ja", "yes"}


def _families(value: Any) -> list[str]:
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def _join(parts: list[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} och {parts[1]}"
    return ", ".join(parts[:-1]) + f" och {parts[-1]}"


def build_confirmed_why_now(record: dict[str, Any] | None) -> dict[str, Any]:
    """Translate independent PIT confirmation into user-facing Swedish text."""
    r = record or {}
    positive = _families(r.get("Förändringsbekräftelse positiva familjer"))
    negative = _families(r.get("Förändringsbekräftelse negativa familjer"))
    history_n = int(r.get("Förändringsbekräftelse historikfamiljer") or 0)
    candidate = _yes(r.get("Förändringsbekräftelse kandidat"))
    strong = _yes(r.get("Förändringsbekräftelse stark"))
    warning = _yes(r.get("Förändringsbekräftelse varning"))

    pos_text = [_FAMILY_POSITIVE.get(x, f"{x.lower()} förbättras") for x in positive]
    neg_text = [_FAMILY_NEGATIVE.get(x, f"{x.lower()} försämras") for x in negative]

    if candidate and len(positive) >= 2 and not negative:
        status = "Bekräftat varför nu"
        if strong and len(positive) >= 3:
            summary = "Tre oberoende förändringar bekräftar caset: " + _join(pos_text) + "."
        else:
            summary = "Varför nu? " + _join(pos_text).capitalize() + "."
        verdict = "starkt bekräftat" if strong else "bekräftat"
        conflict = False
    elif positive and negative:
        status = "Motstridigt varför nu"
        summary = "Borsify ser både stöd och motbevis: " + _join(pos_text) + ", men " + _join(neg_text) + "."
        verdict = "konflikt"
        conflict = True
    elif len(negative) >= 2:
        status = "Bekräftad försämring"
        summary = "Varning: " + _join(neg_text).capitalize() + "."
        verdict = "negativt bekräftat"
        conflict = True
    elif len(positive) == 1:
        status = "Ett positivt förändringsstöd"
        summary = "Ett färskt stöd finns: " + pos_text[0] + ", men förändringen är ännu inte oberoende bekräftad."
        verdict = "ännu inte bekräftat"
        conflict = False
    elif len(negative) == 1:
        status = "Ett tydligt motbevis"
        summary = "Varning: " + neg_text[0] + ". Försämringen är ännu inte brett bekräftad, men ska inte döljas."
        verdict = "motbevis"
        conflict = True
    elif history_n < 2:
        status = "För lite historik"
        summary = "Borsify har ännu inte minst två oberoende förändringsminnen med riktig historik för att verifiera varför caset är intressant just nu."
        verdict = "för lite historik"
        conflict = False
    else:
        status = "Inget bekräftat varför nu"
        summary = "Borsify har flera förändringsminnen, men de visar ännu ingen tillräckligt tydlig gemensam riktning."
        verdict = "ingen bekräftelse"
        conflict = False

    return {
        "Bekräftat varför nu status": status,
        "Bekräftat varför nu": summary,
        "Bekräftat varför nu utfall": verdict,
        "Bekräftat varför nu stöd antal": len(positive),
        "Bekräftat varför nu motbevis antal": len(negative),
        "Bekräftat varför nu konflikt": conflict or warning and bool(negative),
        "Bekräftat varför nu stark": strong and candidate,
        "Bekräftat varför nu familjer": ", ".join(positive),
        "Bekräftat varför nu motbevis": ", ".join(negative),
    }
