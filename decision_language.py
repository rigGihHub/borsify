from __future__ import annotations

import re
from typing import Any


# Presentation-only language layer. It must never be used as model input or to
# change gates/scores; its job is to translate internal finance language into
# ordinary Swedish at the decision surface.
_PHRASE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bpositiv inflektion\b", "utvecklingen har börjat förbättras"),
    (r"\btidiga förbättringstecken\b", "de första tecknen pekar åt rätt håll"),
    (r"\bnegativ inflektion\b", "utvecklingen har börjat försämras"),
    (r"\binflektion\b", "förändring i utvecklingen"),
    (r"\bstark relativ styrka\b", "aktien går bättre än marknaden"),
    (r"\bsvag relativ styrka\b", "aktien går sämre än marknaden"),
    (r"\brelativ styrka\b", "hur aktien går jämfört med marknaden"),
    (r"\b12[–-]1 momentum\b", "kursutveckling på längre sikt"),
    (r"\bmomentum\b", "kursutveckling den senaste tiden"),
    (r"\bestimatrevideringar\b", "ändrade vinstprognoser från analytiker"),
    (r"\bestimatrevidering\b", "ändrad vinstprognos från analytiker"),
    (r"\bestimat\b", "analytikernas prognoser"),
    (r"\bkatalysator\b", "händelse som kan ändra marknadens syn"),
    (r"\bfundamental(?:t|a)?\b", "bolagets ekonomi"),
    (r"\bfundamenta\b", "bolagets ekonomi"),
    (r"\bsetup\b", "köpläge"),
    (r"\bmultipel(?:n|ar|erna)?\b", "värdering"),
    (r"\bvalue trap\b", "värdefälla"),
    (r"\bmispricing\b", "möjlig felprissättning"),
    (r"\bevidens\b", "underlag"),
    (r"\bcase-breaker\b", "sak som skulle få bedömningen att ändras"),
    (r"\bgate\b", "kontroll"),
    (r"\bproxy\b", "ungefärligt mått"),
    (r"\bEPS-estimatrevideringar\b", "ändringar i analytikernas vinstprognoser per aktie"),
    (r"\bEPS-estimat\b", "vinstprognos per aktie"),
    (r"\bEPS\b", "vinst per aktie"),
    (r"\bFCF\b", "fritt kassaflöde"),
    (r"\bCAGR\b", "genomsnittlig årlig förändring"),
)

# Internal labels that add little value on the novice surface when a score is
# already displayed separately.
_SCORE_FRAGMENT = re.compile(
    r"\s*[\[(](?:score|signal|styrka|confidence|readiness)?\s*[:=]?\s*\d+(?:[.,]\d+)?\s*(?:/\s*100|%)?[\])]",
    flags=re.IGNORECASE,
)


def simplify_decision_text(value: Any, *, max_chars: int = 240) -> str:
    """Return compact novice-facing Swedish without altering underlying data.

    The function is intentionally deterministic. It replaces jargon, removes
    duplicate whitespace and trims overlong explanations at a sentence/clause
    boundary. Raw analytical fields remain untouched elsewhere in the app.
    """
    text = str(value if value is not None else "—").strip()
    if not text or text.lower() in {"nan", "none"}:
        return "—"

    text = text.replace("_", " ")
    for pattern, replacement in _PHRASE_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Explain RSI only if it leaks into a decision sentence; raw RSI remains in
    # advanced views. Numeric detail is kept, but the acronym is not required.
    text = re.sub(r"\bRSI\s*(\d+(?:[.,]\d+)?)", r"kursen har nyligen varit pressad, nivå \1", text, flags=re.IGNORECASE)
    text = re.sub(r"\bRSI\b", "kortsiktigt kursläge", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSMA\s*200\b|\bSMA200\b", "långsiktigt kurssnitt", text, flags=re.IGNORECASE)

    text = _SCORE_FRAGMENT.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" ;,.\n\t")
    text = re.sub(r"\s*;\s*", ". ", text)
    text = re.sub(r"\.{2,}", ".", text)

    if max_chars and len(text) > max_chars:
        cut = text[: max_chars + 1]
        # Prefer a natural boundary reasonably close to the limit.
        boundary = max(cut.rfind(". "), cut.rfind(", "), cut.rfind(" och "))
        if boundary >= int(max_chars * 0.55):
            cut = cut[: boundary + (1 if cut[boundary:boundary + 2] == ". " else 0)]
        else:
            cut = cut[:max_chars].rsplit(" ", 1)[0]
        text = cut.rstrip(" ,.;:") + "…"

    if text and text != "—":
        text = text[0].upper() + text[1:]
    return text
