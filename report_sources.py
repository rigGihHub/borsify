from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ReportSource:
    market: str
    source_name: str
    discovery_url: str
    priority: int
    primary: bool
    notes: str

SOURCES = {
    "Sverige": ReportSource("Sverige","Nasdaq Nordic Company News","https://www.nasdaq.com/european-market-activity/news/company-news",1,True,"Bolagens regulatoriska offentliggöranden och issuer reports."),
    "Danmark": ReportSource("Danmark","Nasdaq Nordic Company News","https://www.nasdaq.com/european-market-activity/news/company-news",1,True,"Bolagens regulatoriska offentliggöranden och issuer reports."),
    "Norge": ReportSource("Norge","Euronext Oslo issuer reports","https://live.euronext.com/en/markets/oslo/financial-calendars",1,True,"Finansiell kalender och issuer-publicerade rapporter."),
}

REPORT_TYPES = ("Quarterly Report","Interim Report","Half-yearly Report","Annual Report","Financial Statement Release")

def source_for_country(country: str) -> ReportSource | None:
    return SOURCES.get(str(country or "").strip())

def candidate_report(title: str, published_at: str, url: str, attachment_url: str = "", source: str = "") -> dict[str, Any]:
    low=str(title or "").lower()
    report_type="Other"
    if "annual" in low or "årsrapport" in low: report_type="Annual Report"
    elif "half-year" in low or "halvår" in low: report_type="Half-yearly Report"
    elif "interim" in low or "delårs" in low: report_type="Interim Report"
    elif "quarter" in low or "kvartal" in low or "q1" in low or "q2" in low or "q3" in low or "q4" in low: report_type="Quarterly Report"
    return {"title":title,"published_at":published_at,"url":url,"attachment_url":attachment_url,"source":source,"report_type":report_type,"is_financial_report":report_type!="Other"}

def report_source_status(country: str) -> str:
    src=source_for_country(country)
    if not src:return "Ingen primär rapportkälla konfigurerad för marknaden."
    return f"Primär rapportkälla: {src.source_name}. Borsify ska använda bolagets offentliggjorda rapport före sekundära sammanfattningar."
