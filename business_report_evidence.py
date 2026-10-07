"""Extract attributable business evidence, never certify issuer claims as a moat."""
import re
import pandas as pd

TOPICS = {
    "Verksamhet och segment": r"\b(?:segment|business model|customers|products|verksamhet|affärsmodell|kunder|produkter)\b",
    "Tillväxt och investeringar": r"\b(?:investments?|expansion|launch|research and development|investeringar|lanser|forskning|utveckling)\w*",
    "Efterfrågan och branschrisk": r"\b(?:demand|competition|competitive|regulation|obsolete|declin|efterfrågan|konkurrens|reglering|minsk)\w*",
    "Konkurrensfördel att pröva": r"\b(?:retention|recurring revenue|switching costs|patents?|market share|kundbehållning|återkommande intäkter|byteskostnader|marknadsandel)\b",
}


def extract_business_evidence(text, source_url, published_at, period):
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text).strip())
    evidence = []
    for topic, pattern in TOPICS.items():
        matches = [s for s in sentences if 40 <= len(s) <= 900 and re.search(pattern, s, re.I)]
        # Prefer measurable statements; keep context and negative wording intact.
        matches.sort(key=lambda s: not bool(re.search(r"\d", s)))
        for sentence in list(dict.fromkeys(matches))[:2]:
            evidence.append({"ämne": topic, "text": sentence, "källa": source_url,
                             "publicerad": published_at, "period": period})
    return {"Rapport verksamhetsunderlag": evidence,
            "Rapport verksamhetsstatus": "Bolagets rapportuppgifter; konkurrensfördel och prognos ej oberoende verifierade"}


def usable_business_evidence(row, today=None):
    evidence = row.get("Rapport verksamhetsunderlag")
    if not isinstance(evidence, list) or str(row.get("Rapport text verifierad")).lower() != "true":
        return []
    now = pd.Timestamp(today or pd.Timestamp.now(tz="UTC"))
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    result = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        stamp = pd.to_datetime(item.get("publicerad"), errors="coerce", utc=True)
        if pd.isna(stamp) or not 0 <= (now - stamp).total_seconds() <= 366 * 86400:
            continue
        if item.get("källa") != row.get("Rapport URL") or not str(item.get("källa", "")).startswith("https://"):
            continue
        result.append(item)
    return result
