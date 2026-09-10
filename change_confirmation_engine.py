from __future__ import annotations

"""Cross-family confirmation of *observed changes*.

This layer deliberately does not create a score. It combines only independent
point-in-time memory families that have enough real history to make a change
claim. Missing history is neutral, never positive or negative evidence.
"""

from typing import Any

FAMILIES = (
    ("Rapport", "Rapportminne historik", "Rapportminne förbättring", "Rapportminne försämring", "Rapportminne status"),
    ("Konsensus", "Konsensusminne historik", "Konsensusminne positiv", "Konsensusminne negativ", "Konsensusminne status"),
    ("Ledning", "Ledningsminne historik", "Ledningsminne positiv", "Ledningsminne negativ", "Ledningsminne status"),
)


def _yes(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "ja", "yes"}


def build_change_confirmation(record: dict[str, Any] | None) -> dict[str, Any]:
    """Combine independent PIT change families without collapsing them to a score."""
    r = record or {}
    available: list[str] = []
    positive: list[str] = []
    negative: list[str] = []
    detail: list[str] = []

    for label, history_key, positive_key, negative_key, status_key in FAMILIES:
        if not _yes(r.get(history_key)):
            continue
        available.append(label)
        pos = _yes(r.get(positive_key))
        neg = _yes(r.get(negative_key))
        # Contradictory flags inside one family are not independent confirmation.
        if pos and not neg:
            positive.append(label)
        elif neg and not pos:
            negative.append(label)
        status = str(r.get(status_key) or "").strip()
        if status:
            detail.append(f"{label}: {status}")

    if len(available) < 2:
        status = "För lite oberoende förändringshistorik"
        candidate = False
        strong = False
        warning = False
        explanation = "Minst två oberoende PIT-minnen med verklig historik krävs innan Borsify kallar en förändring bekräftad."
    elif len(positive) >= 2 and not negative:
        status = "Förändringen bekräftas från flera håll"
        candidate = True
        strong = len(positive) >= 3
        warning = False
        explanation = f"Oberoende förändringssignaler pekar åt samma positiva håll: {', '.join(positive)}."
    elif len(negative) >= 2 and not positive:
        status = "Försämringen bekräftas från flera håll"
        candidate = False
        strong = False
        warning = True
        explanation = f"Flera oberoende förändringssignaler pekar negativt: {', '.join(negative)}."
    elif positive and negative:
        status = "Förändringssignalerna säger emot varandra"
        candidate = False
        strong = False
        warning = True
        explanation = f"Positivt: {', '.join(positive)}. Negativt: {', '.join(negative)}. Borsify behandlar detta som konflikt, inte som bekräftelse."
    elif len(positive) == 1:
        status = "Positiv förändring – ännu inte bekräftad"
        candidate = False
        strong = False
        warning = False
        explanation = f"{positive[0]} förbättras, men minst en ytterligare oberoende familj måste bekräfta förändringen."
    elif len(negative) == 1:
        status = "Negativ förändring – ännu inte brett bekräftad"
        candidate = False
        strong = False
        warning = True
        explanation = f"{negative[0]} försämras. Det är ett motbevis även om försämringen ännu inte bekräftas av flera familjer."
    else:
        status = "Ingen samstämmig förändring ännu"
        candidate = False
        strong = False
        warning = False
        explanation = "Flera PIT-minnen finns, men de visar ännu ingen tydlig gemensam riktning."

    return {
        "Förändringsbekräftelse status": status,
        "Förändringsbekräftelse kandidat": candidate,
        "Förändringsbekräftelse stark": strong,
        "Förändringsbekräftelse varning": warning,
        "Förändringsbekräftelse historikfamiljer": len(available),
        "Förändringsbekräftelse positiva familjer": ", ".join(positive),
        "Förändringsbekräftelse negativa familjer": ", ".join(negative),
        "Förändringsbekräftelse detalj": " | ".join(detail),
        "Förändringsbekräftelse förklaring": explanation,
    }
