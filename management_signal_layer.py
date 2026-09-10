from __future__ import annotations

"""Management Signal Layer.

Conservative extraction of *explicit* management statements from fresh Yahoo news
headlines. This is not generic sentiment analysis and it is not a transcript model.
A statement only counts when the headline explicitly attributes concrete operating
language to management (CEO/CFO/VD/ledning) and matches a predefined topic.

The layer deliberately creates no investment score. Missing or ambiguous language
stays missing, and one isolated statement cannot open a discovery doorway.
"""

import re
from typing import Any

import pandas as pd

_MANAGEMENT = re.compile(r"\b(ceo|cfo|chief executive|chief financial officer|vd|verkställande direktör|ledning(?:en)?)\b", re.I)

TOPICS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    (
        "Efterfrågan",
        re.compile(r"\b(demand (?:is )?(?:improv|strength|recover|accelerat)\w*|efterfrågan (?:ökar|stärks|förbättras|återhämtas))\b", re.I),
        re.compile(r"\b(demand (?:is )?(?:weak|soft|slow|declin|deteriorat)\w*|efterfrågan (?:minskar|försvagas|är svag|bromsar))\b", re.I),
    ),
    (
        "Orderläge",
        re.compile(r"\b(order(?:s| intake| book)? (?:improv|strength|grow|accelerat|record)\w*|orderingång(?:en)? (?:ökar|stärks|växer|rekord))\b", re.I),
        re.compile(r"\b(order(?:s| intake| book)? (?:weak|soft|slow|declin|fall)\w*|orderingång(?:en)? (?:minskar|försvagas|faller|bromsar))\b", re.I),
    ),
    (
        "Marginal",
        re.compile(r"\b(margin(?:s)? (?:improv|expand|strength)\w*|marginal(?:en|er)? (?:förbättras|stärks|ökar))\b", re.I),
        re.compile(r"\b(margin(?:s)? (?:pressure|compress|weaken|declin)\w*|marginal(?:en|er)? (?:pressas|försvagas|minskar))\b", re.I),
    ),
    (
        "Prissättning",
        re.compile(r"\b(pricing (?:power|improv|remain(?:s)? strong)|price increases? (?:stick|hold)|prissättning(?:en)? (?:stärks|är stark)|prishöjningar fungerar)\b", re.I),
        re.compile(r"\b(pricing (?:pressure|weak|deteriorat)|price pressure|prissättning(?:en)? (?:pressas|försvagas)|prispress)\b", re.I),
    ),
    (
        "Lager",
        re.compile(r"\b(inventor(?:y|ies) (?:normaliz|declin|improv)\w*|lager(?:nivåerna|n)? (?:normaliseras|minskar|förbättras))\b", re.I),
        re.compile(r"\b(inventor(?:y|ies) (?:build|rise|elevated|high)|lager(?:nivåerna|n)? (?:ökar|är höga|byggs upp))\b", re.I),
    ),
    (
        "Investeringar",
        re.compile(r"\b(capex (?:disciplined|normaliz|declin)|investment(?:s)? (?:disciplined|normaliz)|investering(?:ar|arna)? (?:disciplinerade|normaliseras))\b", re.I),
        re.compile(r"\b(capex (?:surge|rise|increase)|investment(?:s)? (?:surge|rise sharply)|investering(?:ar|arna)? (?:ökar kraftigt|stiger kraftigt))\b", re.I),
    ),
)


def _headline_items(catalyst_events: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(catalyst_events, dict):
        return []
    news = catalyst_events.get("news")
    return [x for x in news if isinstance(x, dict) and str(x.get("title") or "").strip()] if isinstance(news, list) else []


def build_management_signal(catalyst_events: dict[str, Any] | None) -> dict[str, Any]:
    positives: list[str] = []
    negatives: list[str] = []
    matched_titles: list[str] = []
    topic_seen: set[str] = set()

    for item in _headline_items(catalyst_events)[:10]:
        title = str(item.get("title") or "").strip()
        if not _MANAGEMENT.search(title):
            continue
        for topic, pos_re, neg_re in TOPICS:
            if topic in topic_seen:
                continue
            if neg_re.search(title):
                negatives.append(topic)
                topic_seen.add(topic)
                matched_titles.append(title)
                break
            if pos_re.search(title):
                positives.append(topic)
                topic_seen.add(topic)
                matched_titles.append(title)
                break

    comparable = len(positives) + len(negatives)
    candidate = bool(len(positives) >= 2 and len(negatives) == 0)
    warning = bool(len(negatives) >= 1)
    strong = bool(len(positives) >= 3 and len(negatives) == 0)

    if warning and positives:
        status = "Ledningen ger motstridiga operativa signaler"
    elif len(negatives) >= 2:
        status = "Ledningen beskriver bred försämring"
    elif len(negatives) == 1:
        status = "Ledningen beskriver en ny försämring"
    elif strong:
        status = "Ledningen beskriver bred förbättring"
    elif candidate:
        status = "Ledningen beskriver flera förbättringar"
    elif len(positives) == 1:
        status = "En konkret ledningsförbättring observerad"
    else:
        status = "Ingen verifierbar förändring i ledningsspråk"

    parts: list[str] = []
    if positives:
        parts.append("positivt: " + ", ".join(positives))
    if negatives:
        parts.append("negativt: " + ", ".join(negatives))
    if not parts:
        parts.append("inga explicita CEO/CFO/VD-uttalanden om efterfrågan, order, marginal, pris, lager eller investeringar i färska rubriker")

    return {
        "Ledningssignal status": status,
        "Ledningssignal kandidat": candidate,
        "Ledningssignal stark": strong,
        "Ledningssignal varning": warning,
        "Ledningssignal positiva": int(len(positives)),
        "Ledningssignal negativa": int(len(negatives)),
        "Ledningssignal jämförbara": int(comparable),
        "Ledningssignal positiva ämnen": ", ".join(positives),
        "Ledningssignal negativa ämnen": ", ".join(negatives),
        "Ledningssignal rubriker": " | ".join(dict.fromkeys(matched_titles)),
        "Ledningssignal förklaring": "; ".join(parts),
    }


def select_management_signal_candidates(df: pd.DataFrame, quota: int = 1) -> list[tuple[Any, str]]:
    if df is None or df.empty or quota <= 0 or "Ledningssignal kandidat" not in df.columns:
        return []
    work = df[df["Ledningssignal kandidat"].fillna(False).astype(bool)].copy()
    if work.empty:
        return []
    work["__strong"] = work.get("Ledningssignal stark", False).fillna(False).astype(int)
    work["__pos"] = pd.to_numeric(work.get("Ledningssignal positiva"), errors="coerce").fillna(0)
    work["__neg"] = pd.to_numeric(work.get("Ledningssignal negativa"), errors="coerce").fillna(99)
    work["__ticker"] = work.get("Ticker", pd.Series("", index=work.index)).astype(str)
    work = work.sort_values(["__strong", "__pos", "__neg", "__ticker"], ascending=[False, False, True, True])
    return [(idx, "Ledningssignal") for idx in work.index[:quota]]
