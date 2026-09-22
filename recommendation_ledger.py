from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, timedelta
from typing import Any, Iterable

import numpy as np
import pandas as pd


SHORT_HORIZONS = {"1m": 21, "3m": 63, "6m": 126}
LONG_HORIZONS = {"6m": 126, "1y": 252, "2y": 504}


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _safe(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return None if not math.isfinite(float(value)) else float(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        return pd.Timestamp(value).isoformat()
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if pd.isna(value) if not isinstance(value, (str, bool)) else False:
        return None
    return value


def stable_record_id(
    symbol: str,
    horizon_type: str,
    captured_date: str,
    profile: str,
    market: str,
    model_version: str,
) -> str:
    raw = "|".join([
        str(symbol).upper().strip(),
        str(horizon_type).lower().strip(),
        str(captured_date)[:10],
        str(profile).strip(),
        str(market).strip(),
        str(model_version).strip(),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:28]


def snapshot_columns(horizon_type: str) -> list[str]:
    """Fields frozen for future point-in-time audit.

    Keep raw decision inputs and provenance that were actually available when the
    finalist was analysed. Missing values stay missing; the ledger must never fill
    historical gaps with later data.
    """
    common = [
        "Ticker", "Namn", "Pris", "Valuta", "Prisdatum", "Sektor", "Bransch", "Borsify slutbetyg", "Borsify grundbetyg", "Borsify Score",
        "Datatäckning", "Data Failure status", "Data Failure blockerare", "Data Failure försvagat", "Data Failure fungerande", "Data Failure penalty", "Data Failure förklaring", "Analysis Confidence", "Analysis Confidence Score", "Analysis Confidence nivå", "Analysis Confidence blockerare", "Analysis Confidence varningar", "Analysis Confidence förklaring", "Analysis Confidence datatäckning", "Analysis Confidence källhälsa", "Analysis Confidence bransch-KPI", "Analysis Confidence djup", "Analysis Confidence evidens", "Decision Support", "Decision Support quadrant", "Decision Support nivå", "Decision Support action", "Decision Support förklaring", "Decision Support conviction", "Decision Support confidence", "Deep source status", "Deep source errors", "Deep source error types", "Deep source attempts", "Deep source circuits open", "Deep source circuit open", "Deep source missing", "P/E", "Forward P/E", "P/B", "EV/EBITDA", "FCF yield",
        "ROE", "Vinstmarginal", "Skuld/eget kapital", "Risk", "Värdering", "Kvalitet", "Marknadsläge",
        "Fundamental hämtad", "_Fundamental cache", "Fundamental source status", "Fundamental source errors", "Fundamental source attempts", "Fundamental circuit open",
        "Idiosynkratisk volatilitet status", "Idiosynkratisk volatilitet",
        "Idiosynkratisk volatilitet andel", "Idiosynkratisk beta", "Idiosynkratisk volatilitet sessioner",
    ]
    catalyst = [
        "Catalyst Signal", "Catalyst Support", "Catalyst Strength", "Catalyst Confidence",
        "Primary Catalyst", "Catalyst Timing", "Catalyst Effect", "Catalyst Evidence",
        "Catalyst Evidence Type", "Catalyst Source", "Catalyst Verification",
        "Catalyst Source Quality", "Catalyst Source Quality Score",
        "Catalyst Independent Support", "Catalyst Why Now", "Catalyst Warnings",
        "Why Now Status", "Why Now Summary", "Why Now Evidence Count", "Why Now Evidence Families",
        "Why Now Contradiction Count", "Why Now Warning", "Why Now Has Independent Catalyst",
        "News Impact Status", "News Impact Summary", "News Impact Fresh Count",
        "News Impact Positive Count", "News Impact Negative Count", "News Impact Underreaction Count",
        "News Impact Primary Title", "News Impact Primary Direction", "News Impact Primary Reaction",
        "News Impact Primary Drift", "News Impact Source Quality", "News Impact Warning",
        "News Flow Status", "News Flow Summary", "News Flow Unique Items 30d",
        "News Flow Recent Items 14d", "News Flow Positive 14d", "News Flow Negative 14d",
        "News Flow Independent Positive 14d", "News Flow Independent Negative 14d",
        "News Flow Early Positive 7d", "News Flow Early Negative 7d",
        "News Flow Prior Positive 15-30d", "News Flow Prior Negative 15-30d",
        "News Flow Direction Shift", "News Flow Distinct Positive Days", "News Flow Price Pattern",
        "News Flow Median Immediate Positive", "News Flow Median Five Day Positive",
        "News Flow Median Positive Drift", "News Flow Warning",
        "News Surprise Status", "News Surprise Summary", "News Surprise Fresh Count",
        "News Surprise Meaningful Count", "News Surprise Primary Title", "News Surprise Primary Type",
        "News Surprise Primary Label", "News Surprise Primary Direction", "News Surprise Strength",
        "News Surprise Immediate Reaction", "News Surprise Five Day Reaction",
        "News Surprise Directional Immediate", "News Surprise Directional Five Day",
        "News Surprise Underreaction", "News Surprise Later Confirmation", "News Surprise Adverse Reaction",
        "News Surprise Reference N", "News Surprise Reference Median Immediate",
        "News Surprise Relative Reaction Gap", "News Surprise Source Quality", "News Surprise Warning",
        "News Event Memory Status", "News Event Memory Summary", "News Event Memory N",
        "News Event Memory Median Immediate", "News Event Memory Median Two Day", "News Event Memory Median Five Day",
        "News Event Memory Current Gap Immediate", "News Event Memory Current Gap Five Day",
        "News Event Memory Confidence", "News Event Memory Event Type", "News Event Memory Direction",
        "News Event Memory Warning",
    ]
    inflection = [
        "Inflection Signal", "Inflection Score", "Varför nu", "Förändringskonflikt",
        "Kvartalsdata antal", "Omsättning YoY senaste kvartal", "Omsättning acceleration",
        "Marginal YoY förändring", "Marginal YoY föregående kvartal", "FCF YoY senaste kvartal", "FCF YoY föregående kvartal", "Vinst YoY senaste kvartal", "Vinst YoY föregående kvartal",
        "Fresh Change Status", "Fresh Change Summary", "Fresh Change Positive Count", "Fresh Change Negative Count",
        "Fresh Change Comparable Metrics", "Fresh Change New Positives", "Fresh Change New Negatives",
        "EPS-estimat förändring", "EPS-estimat jämförelseperiod", "EPS-revisionsbalans",
        "Senaste EPS-överraskning", "Analytiker antal", "Reviderande analytiker senaste period",
        "Analytikertäckning", "Estimat tillförlitlighetsvikt",
        "Post-report status", "Post-report why now", "Post-report datum",
        "Post-report dagar sedan", "Post-report EPS-överraskning", "Post-report reaktion",
        "Post-report fortsatt rörelse", "Post-report analytikerrespons",
        "Post-report stöd", "Post-report varning", "Post-report evidens",
        "Report Delta status", "Report Delta kandidat", "Report Delta underreaktion",
        "Report Delta evidens", "Report Delta positiva", "Report Delta negativa",
        "Report Delta styrkor", "Report Delta varningar", "Report Delta guidance",
        "Report Delta kursreaktion", "Report Delta fortsatt rörelse", "Report Delta förklaring",
        "Report Delta datagrund", "Rapport läst", "Rapport text verifierad",
        "Rapport primärkälla verifierad", "Rapport textlängd", "Rapport källa",
        "Rapport URL", "Rapport kontroll", "Rapport användartext",
        "Kapitalallokering nettoåterköp", "Kapitalallokering återköpsyield",
        "Kapitalallokering emissionsyield", "Kapitalallokering kontantutdelningsyield",
        "Kapitalallokering skuldtrend", "Kapitalallokering nettoskuld", "Insider köp antal", "Insider köpare antal",
        "Insider sälj antal", "Insider köp värde", "Insider kluster", "Insider starkt kluster",
        "Insider period dagar", "Insider förklaring", "Ägarsignal status", "Ägarsignal kandidat",
        "Ägarsignal stark", "Ägarsignal positiva", "Ägarsignal varningar", "Ägarsignal förklaring",
        "Ledningssignal status", "Ledningssignal kandidat", "Ledningssignal stark", "Ledningssignal varning",
        "Ledningssignal positiva", "Ledningssignal negativa", "Ledningssignal jämförbara",
        "Ledningssignal positiva ämnen", "Ledningssignal negativa ämnen", "Ledningssignal rubriker",
        "Ledningssignal förklaring",
        "Ledningsminne status", "Ledningsminne historik", "Ledningsminne positiv", "Ledningsminne negativ",
        "Ledningsminne förbättrade ämnen", "Ledningsminne försämrade ämnen", "Ledningsminne signaldatum",
        "Ledningsminne jämförelsedatum", "Ledningsminne förklaring",
        "Konsensusförändring status", "Konsensusförändring kandidat", "Konsensusförändring stark",
        "Konsensusförändring varning", "Konsensus bullish andel", "Konsensus bearish andel",
        "Konsensus net breadth", "Konsensus breadth förändring", "Konsensus analytiker antal",
        "Konsensus uppgraderingar 45d", "Konsensus nedgraderingar 45d",
        "Konsensus initierad bevakning 45d", "Konsensus aktiva analyshus 45d",
        "Konsensus åtgärdsbalans 45d", "Riktkurs medel", "Riktkurs median", "Riktkurs hög",
        "Riktkurs låg", "Riktkurs dispersion", "Riktkurs potential", "Konsensusförändring förklaring",
        "Förändringsbekräftelse kandidat", "Förändringsbekräftelse stark", "Förändringsbekräftelse positiva familjer",
        "Förändringsbekräftelse positiva familjer antal", "Förändringsbekräftelse negativa familjer",
        "Negativ överreaktion", "Negativ överreaktion nivå", "Negativ överreaktion rangvärde",
        "Negativ överreaktion prisstöt", "Negativ överreaktion stöd", "Negativ överreaktion varningar",
        "Negativ överreaktion förklaring", "Fallande kniv varning",
        "Mispriced acceleration", "Mispriced acceleration nivå", "Mispriced acceleration rangvärde",
        "Mispriced acceleration familjer", "Mispriced acceleration stöd", "Mispriced acceleration varningar",
        "Mispriced acceleration förklaring",
        "Hidden inflection", "Hidden inflection nivå", "Hidden inflection rangvärde",
        "Hidden inflection stöd", "Hidden inflection varningar", "Hidden inflection förklaring",
        "Ignored compounder", "Ignored compounder nivå", "Ignored compounder rangvärde",
        "Ignored compounder kvalitetspoäng", "Ignored compounder ointressepoäng",
        "Ignored compounder stöd", "Ignored compounder varningar", "Ignored compounder förklaring",
        "Underfollowed Quality", "Underfollowed Quality nivå", "Underfollowed Quality rangvärde",
        "Underfollowed Quality kvalitetspoäng", "Underfollowed Quality analytiker", "Underfollowed Quality nyhetsflöde",
        "Underfollowed Quality stöd", "Underfollowed Quality varningar", "Underfollowed Quality förklaring",
        "Earnings power noise", "Earnings power noise nivå", "Earnings power noise rangvärde",
        "Earnings power temporary verified", "Earnings power headline weakness",
        "Earnings power stöd", "Earnings power varningar", "Earnings power förklaring",
        "Operating leverage", "Operating leverage nivå", "Operating leverage rangvärde",
        "Operating leverage stöd", "Operating leverage varningar", "Operating leverage förklaring",
        "Operating leverage cost base verified",
        "Balance-sheet optionality", "Balance-sheet optionality nivå", "Balance-sheet optionality rangvärde",
        "Balance-sheet optionality nettoskuld", "Balance-sheet optionality nettokassa verifierad",
        "Balance-sheet optionality stöd", "Balance-sheet optionality varningar", "Balance-sheet optionality förklaring",
        "Cash conversion inflection", "Cash conversion inflection nivå", "Cash conversion inflection rangvärde",
        "Cash conversion inflection stöd", "Cash conversion inflection varningar", "Cash conversion inflection förklaring",
        "Margin recovery", "Margin recovery nivå", "Margin recovery rangvärde",
        "Margin recovery stöd", "Margin recovery varningar", "Margin recovery förklaring",
        "Revision breadth", "Revision breadth nivå", "Revision breadth rangvärde", "Revision breadth andel",
        "Revision breadth stöd", "Revision breadth varningar", "Revision breadth förklaring",
        "Deal Conviction", "Deal Conviction nivå", "Deal Conviction Score",
        "Value Trap Test", "Value Trap verdict", "Value Trap nivå", "Value Trap support score", "Value Trap risk score", "Value Trap stöd", "Value Trap varningar", "Value Trap förklaring",
        "Early Mispricing", "Early Mispricing status", "Early Mispricing nivå", "Early Mispricing Score", "Early Mispricing improvement families", "Early Mispricing muted reactions", "Early Mispricing stöd", "Early Mispricing motargument", "Early Mispricing förklaring",
        "Market Blind Spot", "Market Blind Spot status", "Market Blind Spot nivå", "Market Blind Spot Score", "Market Blind Spot families", "Market Blind Spot reasons", "Market Blind Spot counter", "Market Blind Spot förklaring",
        "Catalyst-to-Recognition", "Catalyst-to-Recognition status", "Catalyst-to-Recognition nivå", "Catalyst-to-Recognition Score", "Catalyst-to-Recognition mechanisms", "Catalyst-to-Recognition reasons", "Catalyst-to-Recognition warnings", "Catalyst-to-Recognition förklaring",
        "Recognition Window", "Recognition Window status", "Recognition Window nivå", "Recognition Window Score", "Recognition Window timing input", "Recognition Window payoff", "Recognition Window payoff status", "Recognition Window observed upside", "Recognition Window reasons", "Recognition Window warnings", "Recognition Window förklaring",
        "Market-Implied Expectations", "Market-Implied Expectations status", "Market-Implied Expectations nivå", "Market-Implied Expectations burden", "Market-Implied Expectations improvement families", "Market-Implied Expectations muted reactions", "Market-Implied Expectations evidence count", "Market-Implied Expectations stöd", "Market-Implied Expectations varningar", "Market-Implied Expectations förklaring",
        "Decision Brief beslut", "Decision Brief kort", "Decision Brief tes", "Decision Brief market wrong", "Decision Brief expectations", "Decision Brief recognition", "Decision Brief timing", "Decision Brief payoff", "Decision Brief risk", "Decision Brief invalidation", "Decision Brief confidence",
        "Deal Conviction oberoende familjer", "Deal Conviction familjer", "Deal Conviction negativa familjer",
        "Deal Conviction förklaring",
        "Business profile", "Business key KPIs", "Business observed generic KPIs", "Business KPI gaps", "Business KPI coverage",
        "KPI Omsättning QoQ", "KPI Bruttomarginal", "KPI Rörelsemarginal", "KPI FCF QoQ", "KPI Lager QoQ", "KPI Skuld/eget kapital rapport", "KPI-specifika observerade", "KPI-specifika saknas", "KPI strukturerad täckning",
        "KPI Inflection", "KPI Inflection nivå", "KPI Inflection confidence", "KPI Inflection stöd", "KPI Inflection varningar", "KPI Inflection ledande KPI observerad", "KPI Inflection förklaring",
        "Inflection Sequence", "Inflection Sequence steg", "Inflection Sequence lead days", "Inflection Sequence förklaring",
        "False Start status", "False Start mogna", "False Start confirmed", "False Start false", "False Start confirmation rate", "False Start median dagar", "False Start förklaring", "False Start frozen state",
        "Management execution", "Management execution nivå", "Management execution stöd", "Management execution varningar",
        "Management execution evidens", "Management execution förklaring",
        "Management promise status", "Management promise antal", "Management promise verifierbara", "Management promise levererade", "Management promise träff", "Management promise förklaring",
        "Expectation Gap status", "Expectation Gap kandidat", "Expectation Gap stark", "Expectation Gap varning",
        "Expectation Gap förändringsfamiljer", "Expectation Gap bullish andel", "Expectation Gap analytiker antal",
        "Expectation Gap riktkurs potential", "Expectation Gap förklaring",
        "Sektorläsning status", "Sektorläsning kandidat", "Sektorläsning stark",
        "Sektorläsning källor antal", "Sektorläsning källbolag", "Sektorläsning källa",
        "Sektorläsning nivå", "Sektorläsning förklaring",
        "Värdekedja roll", "Värdekedja status", "Värdekedja kandidat", "Värdekedja stark",
        "Värdekedja källor antal", "Värdekedja källbolag", "Värdekedja relation", "Värdekedja förklaring",
        "Verifierad relation status", "Verifierad relation kandidat", "Verifierad relation stark",
        "Verifierad relation källor antal", "Verifierad relation källbolag", "Verifierad relation typ",
        "Verifierad relation evidens", "Verifierad relation källa", "Verifierad relation förklaring",
        "Relationsförändring status", "Relationsförändring kandidat", "Relationsförändring stark",
        "Relationsförändring typ", "Relationsförändring datum", "Relationsförändring ålder dagar",
        "Relationsförändring materialitet", "Relationsförändring materialitet evidens",
        "Relationsförändring källbolag", "Relationsförändring evidens", "Relationsförändring källa",
        "Relationsförändring förklaring",
    ]
    if horizon_type == "short":
        return common + [
            "Dagsförändring", "1 mån", "3 mån", "6 mån", "12–1 momentum", "12–1 momentum score", "12–1 momentum status", "Volymkvot", "RSI14",
            "Avstånd SMA200", "Omsättning MSEK/dag",
            "Short Alpha Score", "Short Alpha Gate", "Short Alpha Confidence",
            "Short Relative Strength", "Short Trend", "Short Momentum",
            "Short Recent Momentum", "Short 12–1 Momentum", "Short 12–1 Momentum Return", "Short Momentum Text",
            "Short Participation", "Short Revisions", "Short Catalyst",
            "Short Confirmation Count", "Short Why Now", "Short Counterargument",
            "Short Vetoes", "Short Cautions", "Short Data Warning",
        ] + inflection + catalyst
    return common + [
        "INVEST Score", "Growth Score", "Djupurval", "Djupurval Nyckel", "Djupurval Linser", "Djupurval Linser text",
        "Lång Score", "Livstid Score", "REVERSAL Score", "1 mån", "3 mån", "6 mån", "Avstånd SMA200",
        "Case Gate", "Case Confidence", "Case Confidence Label", "Case Evidence Count", "Case Evidence Basis",
        "Case Veto Count", "Case Supports", "Case Neutrals", "Case Vetoes",
        "Evidence Families schema", "Evidence Family Support Count", "Evidence Family Warning Count",
        "Evidence Family Covered Count", "Evidence Family Label", "Evidence Family Supports", "Evidence Family Warnings",
        "Evidence Family Pris/värdering", "Evidence Family Pris/värdering text", "Evidence Family Pris/värdering detalj",
        "Evidence Family Bolagskvalitet", "Evidence Family Bolagskvalitet text", "Evidence Family Bolagskvalitet detalj",
        "Evidence Family Förändrade förväntningar", "Evidence Family Förändrade förväntningar text", "Evidence Family Förändrade förväntningar detalj",
        "Evidence Family Kursbekräftelse", "Evidence Family Kursbekräftelse text", "Evidence Family Kursbekräftelse detalj",
        "Evidence Family Händelse/katalysator", "Evidence Family Händelse/katalysator text", "Evidence Family Händelse/katalysator detalj",
        "Evidence Family Risk/motbevis", "Evidence Family Risk/motbevis text", "Evidence Family Risk/motbevis detalj",
        "Djupkontroll", "Value Trap Risk", "Deep Confidence", "Fleråriga styrkor",
        "Fleråriga varningar", "Rapportdatum", "Historik år",
        "Fundamental Data status", "Fundamental Data senaste rapportperiod",
        "Fundamental Data rapportålder dagar", "Fundamental Data årsrapporter",
        "Fundamental Data kvartalsrapporter", "Fundamental Data stopp",
        "Fundamental Data varningar", "Fundamental Data styrkor",
        "Vinstkvalitet status", "Vinstkvalitet varningar", "Vinstkvalitet",
        "Earnings Quality schema", "Periodiseringsrisk status",
        "Accruals/tillgångar senaste", "Accruals/tillgångar median",
        "Vinst minus OCF tillväxtgap", "Positivt OCF andel", "Positivt FCF andel",
        "Investment Discipline schema", "Kapitaldisciplin status", "Kapitaldisciplin profil",
        "Kapitaldisciplin styrkor", "Kapitaldisciplin varningar", "Kapitaldisciplin evidens",
        "Tillgångstillväxt senaste", "Tillgångstillväxt CAGR",
        "Tillgångar minus omsättning tillväxtgap", "Capex/omsättning senaste",
        "Capex/omsättning trend", "Kapitalomsättning senaste", "Kapitalomsättning trend",
        "Operativ avkastning/tillgångar senaste", "Operativ avkastning/tillgångar trend",
        "Mispricing Signal", "Mispricing Confidence", "Scenario Status", "Scenario Verdict",
        "Scenario Asymmetry", "Scenario Confidence", "Scenario Risk Label", "Scenario Note",
        "Fundamental Value Range", "Fundamental Value Range status", "Fundamental Value Range confidence",
        "Fundamental Value Range horizon years", "Fundamental Value Range bear low", "Fundamental Value Range bear high",
        "Fundamental Value Range base low", "Fundamental Value Range base high",
        "Fundamental Value Range bull low", "Fundamental Value Range bull high",
        "Fundamental Value Range base return low", "Fundamental Value Range base return high",
        "Fundamental Value Range summary", "Fundamental Value Range assumptions",
        "Fundamental Value Range warnings", "Fundamental Value Range reason",
        "Fundamental Value Range ranking effect",
        "Bear EPS growth", "Bear exit P/E", "Bear upside", "Base EPS growth", "Base exit P/E",
        "Base upside", "Bull EPS growth", "Bull exit P/E", "Bull upside",
        "Varför marknaden kan ha fel", "Devil's Advocate", "Deep fetch error",
    ] + inflection + catalyst


def _pit_critical_fields(horizon_type: str) -> list[str]:
    if horizon_type == "short":
        return ["Ticker", "Pris", "Prisdatum", "Short Alpha Gate", "Short Alpha Score", "Short Alpha Confidence"]
    return [
        "Ticker", "Pris", "Prisdatum", "Case Gate", "INVEST Score", "Case Confidence",
        "Fundamental Data status", "Fundamental Data senaste rapportperiod",
    ]


def point_in_time_snapshot_summary(snapshot: dict[str, Any], horizon_type: str) -> dict[str, Any]:
    """Describe ledger completeness without treating missing data as negative evidence."""
    critical = _pit_critical_fields(str(horizon_type).lower().strip())
    missing = []
    for key in critical:
        value = snapshot.get(key)
        if value is None or (isinstance(value, str) and value.strip() in {"", "—"}):
            missing.append(key)
    present = len(critical) - len(missing)
    return {
        "critical_fields": len(critical),
        "critical_present": present,
        "critical_missing": missing,
        "complete": len(missing) == 0,
    }


def build_recommendation_records(
    frame: pd.DataFrame,
    horizon_type: str,
    model_version: str,
    profile: str,
    market: str,
    captured_at: datetime | pd.Timestamp | None = None,
    max_records: int = 5,
) -> list[dict[str, Any]]:
    """Freeze the actual model output before future outcomes are known.

    All finalists are stored, not only winners. This is important for calibration:
    otherwise the learning dataset would itself suffer from recommendation/survivorship bias.
    """
    if frame is None or frame.empty:
        return []
    horizon_type = str(horizon_type).lower().strip()
    if horizon_type not in {"short", "long"}:
        raise ValueError("horizon_type must be 'short' or 'long'")

    captured = pd.Timestamp(captured_at or pd.Timestamp.now(tz="UTC"))
    if captured.tzinfo is None:
        captured = captured.tz_localize("UTC")
    captured_date = captured.date().isoformat()

    records: list[dict[str, Any]] = []
    keep = snapshot_columns(horizon_type)
    for rank, (_, row) in enumerate(frame.head(max_records).iterrows(), start=1):
        symbol = str(row.get("Ticker", "")).upper().strip()
        price = _num(row.get("Pris"))
        if not symbol or not math.isfinite(price) or price <= 0:
            continue

        snap = {key: _safe(row.get(key)) for key in keep if key in row.index}
        if horizon_type == "short":
            gate = str(row.get("Short Alpha Gate", "—"))
            score = _num(row.get("Short Alpha Score"))
            confidence = _num(row.get("Short Alpha Confidence"))
            why_now = str(row.get("Short Why Now", "—"))
            evidence_count = _num(row.get("Short Confirmation Count"))
        else:
            gate = str(row.get("Case Gate", "—"))
            score = _num(row.get("INVEST Score"))
            confidence = _num(row.get("Case Confidence"))
            why_now = str(row.get("Catalyst Why Now") or row.get("Varför nu") or "—")
            evidence_count = _num(row.get("Case Evidence Count"))

        # Freeze the actual decision state inside snapshot_json. This avoids trying
        # to reconstruct an old decision later with a newer model version.
        if horizon_type == "short":
            recommended = gate in {"Kortsiktigt toppcase", "Starkt kortsiktigt case"}
            decision_basis = "Short Alpha Gate"
        else:
            recommended = gate in {"Toppcase", "Starkt case"}
            decision_basis = "Case Gate"
        snap["Ledger Decision"] = "RECOMMENDED" if recommended else "NOT_RECOMMENDED"
        snap["Ledger Decision Basis"] = decision_basis
        snap["Ledger Rank"] = rank
        # Point-in-time envelope: provenance is frozen beside the model inputs so
        # future diagnostics never need to infer what version/date/profile was used.
        snap["PIT Schema Version"] = 2
        snap["PIT Model Version"] = str(model_version)
        snap["PIT Captured At"] = captured.isoformat()
        snap["PIT Captured Date"] = captured_date
        snap["PIT Profile"] = str(profile)
        snap["PIT Market"] = str(market)
        pit = point_in_time_snapshot_summary(snap, horizon_type)
        snap["PIT Critical Fields"] = pit["critical_fields"]
        snap["PIT Critical Present"] = pit["critical_present"]
        snap["PIT Critical Missing"] = pit["critical_missing"]
        snap["PIT Complete"] = pit["complete"]

        record_id = stable_record_id(
            symbol, horizon_type, captured_date, profile, market, model_version
        )
        records.append({
            "record_id": record_id,
            "symbol": symbol,
            "name": str(row.get("Namn", symbol)),
            "horizon_type": horizon_type,
            "model_version": str(model_version),
            "profile": str(profile),
            "market": str(market),
            "rank": rank,
            "entry_price": price,
            "gate": gate,
            "score": None if not math.isfinite(score) else float(score),
            "final_score": None if not math.isfinite(_num(row.get("Borsify slutbetyg"))) else float(_num(row.get("Borsify slutbetyg"))),
            "raw_borsify_score": None if not math.isfinite(_num(row.get("Borsify grundbetyg", row.get("Borsify Score")))) else float(_num(row.get("Borsify grundbetyg", row.get("Borsify Score")))),
            "confidence": None if not math.isfinite(confidence) else float(confidence),
            "evidence_count": None if not math.isfinite(evidence_count) else int(evidence_count),
            "why_now": why_now,
            "primary_catalyst": str(row.get("Primary Catalyst", "—")),
            "captured_date": captured_date,
            "captured_at": captured.isoformat(),
            "snapshot_json": json.dumps(snap, ensure_ascii=False, sort_keys=True),
        })
    return records


def deep_selection_outcome_summary(
    recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str = "1y"
) -> pd.DataFrame:
    """Summarise realised outcomes by the frozen primary deep-selection path.

    This is descriptive audit data only. It must not automatically retune model
    weights; small samples are particularly easy to over-interpret.
    """
    columns = ["selection_path", "evaluated", "positive_rate", "mean_return", "median_return"]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=columns)
    if "snapshot_json" not in recommendations.columns or "record_id" not in recommendations.columns:
        return pd.DataFrame(columns=columns)

    recs = recommendations.copy()
    def path_from_snapshot(raw: Any) -> str:
        try:
            snap = json.loads(raw) if isinstance(raw, str) else (raw or {})
            return str(snap.get("Djupurval Nyckel") or "unknown")
        except Exception:
            return "unknown"
    recs["selection_path"] = recs["snapshot_json"].map(path_from_snapshot)
    recs = recs[recs["selection_path"] != "unknown"]
    if recs.empty:
        return pd.DataFrame(columns=columns)

    outs = outcomes.copy()
    if "horizon" in outs.columns:
        outs = outs[outs["horizon"].astype(str) == str(horizon)]
    merged = outs.merge(recs[["record_id", "selection_path"]], on="record_id", how="inner")
    merged["return_pct"] = pd.to_numeric(merged.get("return_pct"), errors="coerce")
    merged = merged.dropna(subset=["return_pct"])
    if merged.empty:
        return pd.DataFrame(columns=columns)

    grouped = merged.groupby("selection_path", dropna=False)["return_pct"]
    result = grouped.agg(evaluated="size", mean_return="mean", median_return="median").reset_index()
    positive = merged.assign(_positive=merged["return_pct"] > 0).groupby("selection_path")["_positive"].mean()
    result["positive_rate"] = result["selection_path"].map(positive)
    return result[columns].sort_values(["evaluated", "mean_return"], ascending=[False, False]).reset_index(drop=True)


def horizons_for_record(record: dict[str, Any]) -> dict[str, int]:
    return SHORT_HORIZONS.copy() if str(record.get("horizon_type")) == "short" else LONG_HORIZONS.copy()


def target_date(captured_date: str, trading_days: int) -> pd.Timestamp:
    """Calendar approximation used only to decide when an outcome is due.

    Exact outcome price is selected by trading-session count from price history below.
    """
    start = pd.Timestamp(captured_date)
    calendar_days = int(round(trading_days * 365.25 / 252))
    return start + pd.Timedelta(days=calendar_days)


def evaluate_record_from_history(
    record: dict[str, Any],
    history: pd.DataFrame,
    as_of: datetime | pd.Timestamp | None = None,
    benchmark_history: pd.DataFrame | None = None,
    benchmark_symbol: str | None = None,
    benchmark_name: str | None = None,
) -> list[dict[str, Any]]:
    """Evaluate due horizons using trading-session offsets after the recommendation date.

    The function never uses a price before captured_date and never substitutes today's
    price for a missed historical horizon. This keeps outcomes reproducible.
    """
    if history is None or history.empty or "Close" not in history:
        return []

    work = history[["Close"]].copy()
    work.index = pd.to_datetime(work.index)
    if getattr(work.index, "tz", None) is not None:
        work.index = work.index.tz_localize(None)
    work = work.sort_index()
    work = work[np.isfinite(pd.to_numeric(work["Close"], errors="coerce"))]
    if work.empty:
        return []

    captured = pd.Timestamp(str(record.get("captured_date"))[:10])
    asof = pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC"))
    if asof.tzinfo is not None:
        asof = asof.tz_localize(None)
    entry_price = _num(record.get("entry_price"))
    if not math.isfinite(entry_price) or entry_price <= 0:
        return []

    after = work[work.index.normalize() >= captured.normalize()]
    if after.empty:
        return []

    out = []
    for label, trading_days in horizons_for_record(record).items():
        # session 0 is the first market close on/after capture date.
        if len(after) <= trading_days:
            continue
        row = after.iloc[trading_days]
        eval_date = after.index[trading_days]
        if eval_date > asof:
            continue
        price = _num(row["Close"])
        if not math.isfinite(price) or price <= 0:
            continue
        ret = price / entry_price - 1

        # Path quality from recommendation date through the frozen horizon. These
        # diagnostics are descriptive: they show how quickly the thesis worked and
        # how painful the path was, without changing the original recommendation.
        path = after.iloc[:trading_days + 1].copy()
        path_prices = pd.to_numeric(path["Close"], errors="coerce")
        path_returns = path_prices / entry_price - 1
        best_return = float(path_returns.max()) if path_returns.notna().any() else np.nan
        worst_return = float(path_returns.min()) if path_returns.notna().any() else np.nan
        sessions_to_best = None
        if path_returns.notna().any():
            best_idx = path_returns.idxmax()
            try:
                sessions_to_best = int(path.index.get_loc(best_idx))
            except Exception:
                sessions_to_best = None

        benchmark_return = np.nan
        if benchmark_history is not None and not benchmark_history.empty and "Close" in benchmark_history:
            bench = benchmark_history[["Close"]].copy()
            bench.index = pd.to_datetime(bench.index)
            if getattr(bench.index, "tz", None) is not None:
                bench.index = bench.index.tz_localize(None)
            bench = bench.sort_index()
            bench["Close"] = pd.to_numeric(bench["Close"], errors="coerce")
            bench = bench.dropna(subset=["Close"])
            # Use the first benchmark close on/after capture and the last close on/before
            # the stock's evaluated date. This avoids requiring identical exchange calendars.
            b0 = bench[bench.index.normalize() >= captured.normalize()]
            b1 = bench[bench.index.normalize() <= pd.Timestamp(eval_date).normalize()]
            if not b0.empty and not b1.empty:
                b_start = _num(b0.iloc[0]["Close"])
                b_end = _num(b1.iloc[-1]["Close"])
                if math.isfinite(b_start) and b_start > 0 and math.isfinite(b_end) and b_end > 0:
                    benchmark_return = b_end / b_start - 1
        excess_return = ret - benchmark_return if math.isfinite(benchmark_return) else np.nan

        out.append({
            "record_id": str(record["record_id"]),
            "symbol": str(record["symbol"]),
            "horizon": label,
            "trading_days": int(trading_days),
            "evaluated_date": pd.Timestamp(eval_date).date().isoformat(),
            "evaluated_price": float(price),
            "return_pct": float(ret),
            "benchmark_symbol": str(benchmark_symbol or ""),
            "benchmark_name": str(benchmark_name or ""),
            "benchmark_return_pct": None if not math.isfinite(benchmark_return) else float(benchmark_return),
            "excess_return_pct": None if not math.isfinite(excess_return) else float(excess_return),
            "beat_benchmark": None if not math.isfinite(excess_return) else bool(excess_return > 0),
            "best_return_pct": None if not math.isfinite(best_return) else float(best_return),
            "worst_return_pct": None if not math.isfinite(worst_return) else float(worst_return),
            "sessions_to_best": sessions_to_best,
            "positive": bool(ret > 0),
            "gain_10": bool(ret >= 0.10),
            "loss_10": bool(ret <= -0.10),
            "evaluated_at": pd.Timestamp(as_of or pd.Timestamp.now(tz="UTC")).isoformat(),
        })
    return out


def outcome_summary(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return {
            "status": "För lite utfallsdata",
            "evaluated": 0,
            "message": "Borsify behöver fler mogna rekommendationer innan resultat kan bedömas.",
        }
    merged = outcomes.merge(
        recommendations[["record_id", "horizon_type", "gate", "score", "confidence", "model_version"]],
        on="record_id",
        how="left",
    )
    valid = merged.dropna(subset=["return_pct"])
    if valid.empty:
        return {
            "status": "För lite utfallsdata",
            "evaluated": 0,
            "message": "Inga rekommendationer har ännu ett mätbart utfall.",
        }
    return {
        "status": "Utfall finns – ännu inte statistiskt bevis",
        "evaluated": int(len(valid)),
        "median_return": float(valid["return_pct"].median()),
        "mean_return": float(valid["return_pct"].mean()),
        "hit_rate": float((valid["return_pct"] > 0).mean()),
        "gain_10_rate": float((valid["return_pct"] >= 0.10).mean()),
        "loss_10_rate": float((valid["return_pct"] <= -0.10).mean()),
        "benchmark_evaluated": int(pd.to_numeric(valid.get("excess_return_pct"), errors="coerce").notna().sum()) if "excess_return_pct" in valid.columns else 0,
        "median_excess_return": float(pd.to_numeric(valid["excess_return_pct"], errors="coerce").dropna().median()) if "excess_return_pct" in valid.columns and pd.to_numeric(valid["excess_return_pct"], errors="coerce").notna().any() else np.nan,
        "beat_benchmark_rate": float((pd.to_numeric(valid["excess_return_pct"], errors="coerce").dropna() > 0).mean()) if "excess_return_pct" in valid.columns and pd.to_numeric(valid["excess_return_pct"], errors="coerce").notna().any() else np.nan,
        "mean_excess_return": float(pd.to_numeric(valid["excess_return_pct"], errors="coerce").dropna().mean()) if "excess_return_pct" in valid.columns and pd.to_numeric(valid["excess_return_pct"], errors="coerce").notna().any() else np.nan,
        "median_sessions_to_best": float(pd.to_numeric(valid["sessions_to_best"], errors="coerce").dropna().median()) if "sessions_to_best" in valid.columns and pd.to_numeric(valid["sessions_to_best"], errors="coerce").notna().any() else np.nan,
        "message": "Deskriptiv uppföljning av frysta point-in-time-rekommendationer. Jämförelsen mot index är ungefärlig och resultatet är inte ett bevis på framtida överavkastning.",
    }


def outcome_summary_by_horizon(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Compare matured results separately so unlike holding periods are never mixed."""
    cols=["Tid efter förslaget","Antal","Typiskt resultat","Snittresultat","Typiskt mot index","Snitt mot index","Slog index"]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    rows=[]
    for horizon, group in outcomes.groupby("horizon", dropna=False):
        summary=outcome_summary(recommendations, group)
        if not summary.get("evaluated",0):
            continue
        rows.append({
            "Tid efter förslaget":str(horizon),
            "Antal":int(summary["evaluated"]),
            "Typiskt resultat":summary.get("median_return",np.nan),
            "Snittresultat":summary.get("mean_return",np.nan),
            "Typiskt mot index":summary.get("median_excess_return",np.nan),
            "Snitt mot index":summary.get("mean_excess_return",np.nan),
            "Slog index":summary.get("beat_benchmark_rate",np.nan),
        })
    return pd.DataFrame(rows,columns=cols)

def calibration_by_final_score(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    """Test whether higher frozen final scores actually correspond to better later outcomes."""
    empty={"status":"För lite data","eligible":0,"table":pd.DataFrame(),"monotonic":None}
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return empty
    if "final_score" not in recommendations.columns:
        return empty
    o=outcomes[outcomes["horizon"].astype(str).eq(str(horizon))].copy()
    if o.empty:return empty
    merged=o.merge(recommendations[["record_id","final_score"]],on="record_id",how="left")
    merged["final_score"]=pd.to_numeric(merged["final_score"],errors="coerce")
    merged["return_pct"]=pd.to_numeric(merged["return_pct"],errors="coerce")
    merged=merged.dropna(subset=["final_score","return_pct"])
    if merged.empty:return empty
    bins=[-0.001,59.999,69.999,79.999,89.999,100.001]
    labels=["0–59","60–69","70–79","80–89","90–100"]
    merged["Betyg"]=pd.cut(merged["final_score"],bins=bins,labels=labels,include_lowest=True)
    rows=[]
    for label,g in merged.groupby("Betyg",observed=False):
        if g.empty:continue
        excess=pd.to_numeric(g.get("excess_return_pct"),errors="coerce") if "excess_return_pct" in g.columns else pd.Series(dtype=float)
        rows.append({"Borsify-betyg":str(label),"Antal":int(len(g)),"Typiskt resultat":float(g["return_pct"].median()),"Snittresultat":float(g["return_pct"].mean()),"Slog index":float((excess.dropna()>0).mean()) if excess.notna().any() else np.nan,"Typiskt mot index":float(excess.dropna().median()) if excess.notna().any() else np.nan})
    table=pd.DataFrame(rows)
    mature=table[table["Antal"]>=5].copy() if not table.empty else table
    monotonic=None
    if len(mature)>=3:
        order={v:i for i,v in enumerate(labels)}
        mature["_o"]=mature["Borsify-betyg"].map(order)
        vals=mature.sort_values("_o")["Typiskt mot index"].dropna().tolist()
        if len(vals)>=3:monotonic=all(b>=a for a,b in zip(vals,vals[1:]))
    return {"status":"Data finns – ännu inte statistiskt bevis" if len(merged)>=20 else "För lite data för säker slutsats","eligible":int(len(merged)),"table":table,"monotonic":monotonic}


def score_calibration_warning(calibration: dict[str, Any]) -> str:
    """Conservative user-facing interpretation; never promote from tiny samples."""
    n=int(calibration.get("eligible",0) or 0)
    monotonic=calibration.get("monotonic")
    if n < 20:
        return f"För få kontrollerade förslag ({n}) för att bedöma betygsskalan säkert."
    if monotonic is False:
        return "Varning: högre Borsify-betyg har ännu inte gett tydligt bättre framtida resultat. Tolka små poängskillnader försiktigt."
    if monotonic is True:
        return "Högre Borsify-betyg har hittills hängt ihop med bättre resultat i de grupper som har tillräckligt med data. Det är fortfarande ingen garanti."
    return "Det finns ännu inte tillräckligt många jämförbara betygsgrupper för en säker slutsats."


def calibration_by_gate(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame()
    o = outcomes[outcomes["horizon"] == horizon].copy()
    if o.empty:
        return pd.DataFrame()
    merged = o.merge(
        recommendations[["record_id", "gate", "confidence", "score"]],
        on="record_id",
        how="left",
    ).dropna(subset=["return_pct"])
    if merged.empty:
        return pd.DataFrame()
    rows = []
    for gate, group in merged.groupby("gate", dropna=False):
        rows.append({
            "Gate": str(gate),
            "Antal": int(len(group)),
            "MedianReturn": float(group["return_pct"].median()),
            "MeanReturn": float(group["return_pct"].mean()),
            "HitRate": float((group["return_pct"] > 0).mean()),
            "Gain10": float((group["return_pct"] >= 0.10).mean()),
            "Loss10": float((group["return_pct"] <= -0.10).mean()),
        })
    return pd.DataFrame(rows).sort_values(["MedianReturn", "Antal"], ascending=[False, False])
def calibration_by_deal_conviction(recommendations: pd.DataFrame, outcomes: pd.DataFrame, horizon: str) -> dict[str, Any]:
    """Prospective calibration of the Deal Conviction score frozen at recommendation time.

    Never reconstructs Deal Conviction for older records. Rows without a frozen numeric
    value are excluded, which avoids look-ahead / model-version leakage.
    """
    empty = {
        "status": "För lite prospektiv conviction-data",
        "eligible": 0,
        "excluded_legacy": 0,
        "table": pd.DataFrame(),
        "monotonic": None,
        "message": "Deal Conviction kalibreras först från rekommendationer där värdet faktiskt frystes vid beslutstillfället.",
    }
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return empty
    if "Deal Conviction Score" not in recommendations.columns:
        return empty
    o=outcomes[outcomes["horizon"] == horizon].copy()
    if o.empty:
        return empty
    keep=["record_id","Deal Conviction Score"]
    if "Deal Conviction oberoende familjer" in recommendations.columns:
        keep.append("Deal Conviction oberoende familjer")
    merged=o.merge(recommendations[keep],on="record_id",how="left")
    merged["conviction"]=pd.to_numeric(merged["Deal Conviction Score"],errors="coerce")
    merged["return_pct"]=pd.to_numeric(merged["return_pct"],errors="coerce")
    legacy=int(merged["conviction"].isna().sum())
    valid=merged.dropna(subset=["conviction","return_pct"]).copy()
    if valid.empty:
        out=dict(empty); out["excluded_legacy"]=legacy; return out

    bins=[-0.001,24.999,49.999,74.999,100.001]
    labels=["0–24","25–49","50–74","75–100"]
    valid["Convictiongrupp"]=pd.cut(valid["conviction"],bins=bins,labels=labels,include_lowest=True)
    rows=[]
    for label,g in valid.groupby("Convictiongrupp",observed=False):
        if g.empty: continue
        excess=pd.to_numeric(g.get("excess_return_pct"),errors="coerce") if "excess_return_pct" in g.columns else pd.Series(dtype=float)
        rows.append({
            "Conviction":str(label),
            "Antal":int(len(g)),
            "Medianutfall":float(g["return_pct"].median()),
            "Snittutfall":float(g["return_pct"].mean()),
            "Träff %":float((g["return_pct"]>0).mean()),
            "≥ +10 %":float((g["return_pct"]>=.10).mean()),
            "≤ −10 %":float((g["return_pct"]<=-.10).mean()),
            "Median över index":float(excess.dropna().median()) if not excess.empty and excess.notna().any() else np.nan,
        })
    table=pd.DataFrame(rows)
    # Monotonicity is descriptive only and requires enough observations in every compared bucket.
    mature=table[table["Antal"]>=5].copy() if not table.empty else table
    monotonic=None
    if len(mature)>=3:
        order={"0–24":0,"25–49":1,"50–74":2,"75–100":3}
        mature["_o"]=mature["Conviction"].map(order)
        mature=mature.sort_values("_o")
        vals=mature["Medianutfall"].tolist()
        monotonic=all(b>=a for a,b in zip(vals,vals[1:]))
    status="Prospektiv conviction-data finns – ännu inte statistiskt bevis"
    if len(valid)<20:
        status="För lite prospektiv conviction-data för slutsats"
    return {
        "status":status,
        "eligible":int(len(valid)),
        "excluded_legacy":legacy,
        "table":table,
        "monotonic":monotonic,
        "message":"Endast frysta point-in-time Deal Conviction-värden används. Tabellen är deskriptiv; Borsify ändrar inte vikter automatiskt från små kohorter.",
    }

def outcome_summary_by_type(recommendations: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    """Keep short and long recommendation families separate in validation."""
    cols=["Typ","Förslag","Typiskt resultat","Snittresultat","Jämförda med index","Typiskt mot index","Snitt mot index","Slog index"]
    if recommendations is None or recommendations.empty or outcomes is None or outcomes.empty:
        return pd.DataFrame(columns=cols)
    if "record_id" not in recommendations.columns or "horizon_type" not in recommendations.columns:
        return pd.DataFrame(columns=cols)
    merged=outcomes.merge(recommendations[["record_id","horizon_type"]],on="record_id",how="left")
    rows=[]
    labels={"short":"Sälj snart","long":"Längre sikt"}
    for typ,g in merged.groupby("horizon_type",dropna=False):
        ret=pd.to_numeric(g.get("return_pct"),errors="coerce").dropna()
        excess=pd.to_numeric(g.get("excess_return_pct"),errors="coerce").dropna()
        if ret.empty: continue
        rows.append({
            "Typ":labels.get(str(typ),str(typ)),
            "Förslag":int(len(ret)),
            "Typiskt resultat":float(ret.median()),
            "Snittresultat":float(ret.mean()),
            "Jämförda med index":int(len(excess)),
            "Typiskt mot index":float(excess.median()) if len(excess) else np.nan,
            "Snitt mot index":float(excess.mean()) if len(excess) else np.nan,
            "Slog index":float((excess>0).mean()) if len(excess) else np.nan,
        })
    return pd.DataFrame(rows,columns=cols)
