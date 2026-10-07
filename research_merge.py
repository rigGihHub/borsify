"""Attach research facts without replacing the scanner's scores or prices."""
import pandas as pd

RESEARCH_PREFIXES = ("Deep ", "Rapport", "KPI", "Report Delta", "Business ", "Management ", "Historik ", "Konkurrensfördel ")
RESEARCH_FIELDS = {"Historik år", "Omsättning CAGR", "Vinst CAGR", "FCF CAGR", "Positiv FCF-andel", "Senaste FCF", "Senaste vinst", "Positiv vinst-andel", "Rörelsemarginal trend", "Skuldförändring"}

def merge_research(source, *frames):
    out = source.copy()
    for evidence in frames:
        if evidence.empty or "Ticker" not in evidence:
            continue
        updates = evidence.drop_duplicates("Ticker").set_index("Ticker")
        for column in updates:
            if column in RESEARCH_FIELDS or column.startswith(RESEARCH_PREFIXES):
                values = out["Ticker"].map(updates[column])
                out[column] = values.combine_first(out[column]) if column in out else values
    return out
