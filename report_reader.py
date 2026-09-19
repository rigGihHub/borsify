from __future__ import annotations

from typing import Any
import re

REPORT_TERMS = {
    "guidance": ["guidance","prognos","outlook","utsikter","mål"],
    "orders": ["orderingång","order intake","orderbok","order book","backlog"],
    "margins": ["marginal","margin","ebit","ebita","ebitda"],
    "cashflow": ["kassaflöde","cash flow","free cash flow","fcf"],
    "one_offs": ["engång","one-off","non-recurring","jämförelsestörande"],
    "risks": ["risk","osäker","uncertain","headwind","motvind"],
}

def report_reader_fields(text: str, source_url: str = "", published_at: str = "") -> dict[str, Any]:
    """Conservative extraction from issuer report text. No unsupported inference."""
    clean=re.sub(r"\s+"," ",str(text or "")).strip()
    low=clean.lower()
    found={key:any(term in low for term in terms) for key,terms in REPORT_TERMS.items()}
    return {
        "Rapportkälla": source_url,
        "Rapport publicerad": published_at,
        "Rapporttext tillgänglig": bool(clean),
        "Guidance nämns": found["guidance"],
        "Orderläge nämns": found["orders"],
        "Marginaler nämns": found["margins"],
        "Kassaflöde nämns": found["cashflow"],
        "Engångsposter nämns": found["one_offs"],
        "Risker nämns": found["risks"],
        "Rapportläsning status": "Primär rapporttext finns" if clean else "Ingen primär rapporttext hämtad",
    }

def report_reader_user_text(fields: dict[str, Any]) -> str:
    if not fields.get("Rapporttext tillgänglig"):
        return "Borsify har inte läst själva rapporttexten för den här analysen. Bedömningen bygger då främst på strukturerade bolags- och kursdata."
    topics=[]
    for key,label in [("Guidance nämns","framtidsutsikter"),("Orderläge nämns","orderläge"),("Marginaler nämns","marginaler"),("Kassaflöde nämns","kassaflöde"),("Engångsposter nämns","engångsposter"),("Risker nämns","risker")]:
        if fields.get(key):topics.append(label)
    return "Borsify har tillgång till primär rapporttext" + (", där bland annat " + ", ".join(topics) + " hittades." if topics else ".")
