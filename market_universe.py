from __future__ import annotations
from pathlib import Path
from typing import Any
import pandas as pd

REQUIRED_COLUMNS = ("Ticker", "Land", "Nivå")
ALLOWED_LEVELS = {"Kärna", "Bred"}
COUNTRY_SUFFIX = {
    "Sverige": ".ST", "Danmark": ".CO", "Norge": ".OL", "Finland": ".HE",
    "Tyskland": ".DE", "Storbritannien": ".L", "Frankrike": ".PA",
    "Nederländerna": ".AS", "Belgien": ".BR", "Portugal": ".LS",
    "Italien": ".MI", "Spanien": ".MC", "Schweiz": ".SW", "Kanada": ".TO",
    "USA": "",
}


def _clean_catalog(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for c in REQUIRED_COLUMNS:
        if c not in out.columns:
            out[c] = ""
    out["Ticker"] = out["Ticker"].astype(str).str.strip().str.upper()
    out["Land"] = out["Land"].astype(str).str.strip()
    out["Nivå"] = out["Nivå"].astype(str).str.strip()
    return out


def audit_catalog(source: str | Path | pd.DataFrame) -> pd.DataFrame:
    """Audit the static ticker catalog before any provider requests are made.

    This does not claim that a ticker exists or is tradable today. It only catches
    catalog defects that Borsify can verify locally: malformed rows, duplicates,
    unsupported countries/tiers and country/ticker suffix conflicts.
    """
    if isinstance(source, pd.DataFrame):
        raw = source.copy()
    else:
        p = Path(source)
        if not p.exists():
            return pd.DataFrame(columns=[*REQUIRED_COLUMNS, "Katalog QC", "Katalogproblem"])
        try:
            raw = pd.read_csv(p)
        except Exception:
            return pd.DataFrame(columns=[*REQUIRED_COLUMNS, "Katalog QC", "Katalogproblem"])
    if any(c not in raw.columns for c in REQUIRED_COLUMNS):
        return pd.DataFrame(columns=[*REQUIRED_COLUMNS, "Katalog QC", "Katalogproblem"])

    out = _clean_catalog(raw)
    ticker_counts = out["Ticker"].value_counts(dropna=False).to_dict()
    rows: list[dict[str, Any]] = []
    for _, row in out.iterrows():
        ticker, country, level = row["Ticker"], row["Land"], row["Nivå"]
        issues: list[str] = []
        hard = False
        if not ticker or ticker in {"NAN", "NONE"}:
            issues.append("ticker saknas"); hard = True
        if not country or country in {"nan", "None"}:
            issues.append("land saknas"); hard = True
        if country not in COUNTRY_SUFFIX:
            issues.append("land stöds inte av katalogreglerna"); hard = True
        if level not in ALLOWED_LEVELS:
            issues.append("okänd universumnivå"); hard = True
        if ticker_counts.get(ticker, 0) > 1 and ticker:
            issues.append("duplicerad ticker"); hard = True
        suffix = COUNTRY_SUFFIX.get(country)
        if suffix is not None and ticker:
            if country == "USA":
                # Yahoo US symbols normally have no market suffix. Class shares may contain '-'.
                if "." in ticker:
                    issues.append("ticker ser inte ut som USA-format"); hard = True
            elif not ticker.endswith(suffix):
                issues.append(f"ticker matchar inte {country}-suffix {suffix}"); hard = True
        rec = row.to_dict()
        rec["Katalog QC"] = "EXKLUDERA" if hard else "GODKÄND"
        rec["Katalogproblem"] = "; ".join(issues) if issues else "inga lokala katalogfel"
        rows.append(rec)
    return pd.DataFrame(rows)


def catalog_integrity_summary(audit: pd.DataFrame) -> dict[str, int]:
    if audit is None or audit.empty or "Katalog QC" not in audit.columns:
        return {"approved": 0, "excluded": 0, "total": 0, "countries": 0}
    return {
        "approved": int(audit["Katalog QC"].eq("GODKÄND").sum()),
        "excluded": int(audit["Katalog QC"].eq("EXKLUDERA").sum()),
        "total": int(len(audit)),
        "countries": int(audit.loc[audit["Katalog QC"].eq("GODKÄND"), "Land"].nunique()),
    }


def load_avanza_universe(path: str | Path) -> pd.DataFrame:
    audit = audit_catalog(path)
    if audit.empty:
        return pd.DataFrame(columns=REQUIRED_COLUMNS)
    out = audit[audit["Katalog QC"].eq("GODKÄND")][list(REQUIRED_COLUMNS)].copy()
    return out.reset_index(drop=True)


def universe_symbols(df: pd.DataFrame, countries: list[str] | None = None, broad: bool = True) -> list[str]:
    if df is None or df.empty:
        return []
    out = df.copy()
    if "Katalog QC" in out.columns:
        out = out[out["Katalog QC"].eq("GODKÄND")]
    if countries:
        out = out[out["Land"].isin(countries)]
    if not broad:
        out = out[out["Nivå"].eq("Kärna")]
    return out["Ticker"].astype(str).drop_duplicates().tolist()


def coverage_table(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["Land", "Kärna", "Bred tillägg", "Totalt"])
    rows = []
    for country, g in df.groupby("Land", sort=True):
        core = int(g["Nivå"].eq("Kärna").sum())
        ext = int(g["Nivå"].eq("Bred").sum())
        rows.append({"Land": country, "Kärna": core, "Bred tillägg": ext, "Totalt": core + ext})
    return pd.DataFrame(rows).sort_values(["Totalt", "Land"], ascending=[False, True]).reset_index(drop=True)


def breadth_summary(df: pd.DataFrame) -> dict[str, int]:
    if df is None or df.empty:
        return {"countries": 0, "total": 0, "core": 0, "extended": 0}
    return {
        "countries": int(df["Land"].nunique()),
        "total": int(len(df)),
        "core": int(df["Nivå"].eq("Kärna").sum()),
        "extended": int(df["Nivå"].eq("Bred").sum()),
    }
