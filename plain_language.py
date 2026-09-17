from __future__ import annotations

"""One vocabulary for user-facing Borsify text.

Rule: default text should be understandable without finance or developer knowledge.
Technical wording belongs behind an optional details view.
"""

PLAIN_TERMS = {
    "Fundamental Change Radar": "Nya förbättringar i bolagen",
    "Discovery 2.0": "Fler aktier som kan vara värda att undersöka",
    "djupurval": "aktier som Borsify tittar extra noga på",
    "Datakontroll": "Kontroll av informationen",
    "cache": "sparad information från en tidigare kontroll",
    "Förstaval-gaten": "slutkontrollen av dagens bästa förslag",
    "ticker": "aktiens kortnamn",
    "tickers": "aktier",
    "stängningskurs": "senaste användbara aktiepris",
    "fundamentalposter": "sparad bolagsinformation",
    "fundamental data": "information om bolagets ekonomi",
    "Fundamental": "Bolagets ekonomi",
    "Case Readiness": "Hur bra underbyggd analysen är",
    "Value Trap": "Aktien ser billig ut men kan vara billig av en dålig anledning",
    "Analysis Confidence": "Hur säker Borsify är på underlaget",
    "Universe QC": "Kontroll av aktiedatan",
}


def plain_term(text: object) -> str:
    value = str(text or "")
    for technical, simple in sorted(PLAIN_TERMS.items(), key=lambda item: len(item[0]), reverse=True):
        value = value.replace(technical, simple)
    return value


def missing_price_summary(total: int) -> tuple[str, str]:
    n = max(0, int(total))
    return (
        f"{n} aktier kunde inte kontrolleras helt",
        "Borsify fick inte fram tillräckligt bra prisinformation för de här aktierna. "
        "Därför används de inte i dagens förslag där prisinformationen behövs.",
    )


def update_summary(total: int, warnings: int) -> str:
    total = max(0, int(total)); warnings = max(0, int(warnings))
    if warnings:
        return f"Borsify kontrollerade {total} aktier. För {warnings} aktier saknades en del information."
    return f"Borsify kontrollerade {total} aktier och fick fram den information som behövdes."
