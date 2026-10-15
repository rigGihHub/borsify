"""International idea discovery, separate from purchase decisions and microcaps.

Issuer reports are attributed observations, not independent moat verification.
The refreshable screen admits loss-making businesses and has no SEK size cap.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import math
import re

import pandas as pd


REPORTS = {
    "ALAB": dict(name="Astera Labs", theme="Datacenteranslutningar", date="2026-08-04", period="Q2 2026", growth=1.04,
        business="Utvecklar halvledare som flyttar data mellan processorer, minne och nätverk i datacenter.",
        opportunity="Fler sammankopplade AI-processorer kan öka behovet av snabbare dataöverföring. Scorpio-switchar breddar produktutbudet.",
        competition="Kundernas egna lösningar och andra chipbolag kan pressa priser och produktval; teknisk integration måste följas i faktiska designvinster.",
        milestone="Följ Scorpio-leveranser, kundspridning och bruttomarginal när försäljningen växer.",
        risk="Kundkoncentration och en svagare investeringscykel för AI-infrastruktur kan slå hårt.",
        fact="Bolaget rapporterade 104 % omsättningstillväxt jämfört med samma kvartal föregående år.",
        url="https://ir.asteralabs.com/news-releases/news-release-details/astera-labs-reports-second-quarter-2026-financial-results"),
    "CRDO": dict(name="Credo Technology", theme="Datacenteranslutningar", date="2026-09-01", period="Q1 FY2027, slut 2026-08-01", growth=1.147,
        business="Utvecklar kretsar och anslutningslösningar för snabb dataöverföring över koppar och optik.",
        opportunity="Datacenters behov av bandbredd kan skapa efterfrågan på energieffektiva anslutningar.",
        competition="Teknikskiften mellan koppar och optik och konkurrerande kretsar kan ändra vilka produkter kunderna väljer.",
        milestone="Följ kundspridning, produktmix och marginaler när nya anslutningar tas i drift.",
        risk="Enskilda stora kunders investeringar och produktbyten kan göra tillväxten ryckig.",
        fact="Bolaget rapporterade 114,7 % omsättningstillväxt jämfört med samma kvartal föregående år.",
        url="https://investors.credosemi.com/news-events/news/news-details/2026/Credo-Technology-Group-Holding-Ltd-Reports-First-Quarter-of-Fiscal-Year-2027-Financial-Results/default.aspx"),
    "RKLB": dict(name="Rocket Lab", theme="Rymdsystem", date="2026-08-10", period="Q2 2026", growth=.62,
        business="Säljer raketuppskjutningar och bygger komponenter och system för satelliter.",
        opportunity="Fler satelliter kan ge efterfrågan på både uppskjutningar och rymdsystem. Order måste omvandlas till leveranser och kassaflöde.",
        competition="Pris, tillförlitlighet och uppskjutningskapacitet avgör konkurrensen; en orderbok bevisar ingen varaktig konkurrensfördel.",
        milestone="Följ leveranser ur orderboken, utvecklingskostnader och finansiering av nya raketprogram.",
        risk="Tekniska förseningar, misslyckade uppskjutningar och kapitalbehov kan urholka aktieägarvärdet.",
        fact="Bolaget rapporterade 62 % omsättningstillväxt och en orderbok på 2,36 miljarder USD.",
        url="https://investors.rocketlabcorp.com/news-releases/news-release-details/rocket-lab-announces-second-quarter-2026-financial-results-posts"),
    "S": dict(name="SentinelOne", theme="Cybersäkerhet", date="2026-08-27", period="Q2 FY2027, slut 2026-07-31", growth=.21,
        business="Säljer programvara som upptäcker och hanterar säkerhetshot mot företags IT-miljöer.",
        opportunity="Fler digitala angrepp kan öka behovet av automatiserad säkerhet, om kunderna väljer och förnyar bolagets tjänster.",
        competition="Stora säkerhetsplattformar kan paketera konkurrerande funktioner. Följ kundbehållning och försäljningskostnad.",
        milestone="Följ återkommande intäkter, stora kunder och vägen från GAAP-förlust till uthålligt kassaflöde.",
        risk="Prispress och höga kostnader kan bestå trots tillväxt. Justerad vinst är inte samma sak som GAAP-vinst.",
        fact="Bolaget rapporterade 21 % omsättningstillväxt och GAAP-rörelsemarginal på −31 %.",
        url="https://investors.sentinelone.com/press-releases/news-details/2026/SentinelOne-Announces-Second-Quarter-Fiscal-Year-2027-Financial-Results/default.aspx"),
    "IOT": dict(name="Samsara", theme="Uppkopplad industri", date="2026-09-03", period="Q2 FY2027, slut 2026-08-01", growth=.30,
        business="Kopplar upp fordon och fysisk verksamhet med sensorer, kameror och molnprogramvara.",
        opportunity="Kunder kan vilja minska olyckor, energiförbrukning och stillestånd. Tillväxt kräver mätbar nytta som motiverar abonnemangskostnaden.",
        competition="Fordons- och telematikleverantörer konkurrerar om samma budget. Följ merförsäljning och kundbehållning.",
        milestone="Följ återkommande intäkter, kundernas användning och kassaflöde efter investeringar.",
        risk="Svagare transportkonjunktur, integritetskrav och konkurrens kan bromsa nya avtal.",
        fact="Bolaget rapporterade 30 % omsättningstillväxt jämfört med samma kvartal föregående år.",
        url="https://www.sec.gov/Archives/edgar/data/1642896/000162828026060438/samsaraepr-q22027.htm"),
    "AXON": dict(name="Axon Enterprise", theme="Säkerhetssystem", date="2026-08-05", period="Q2 2026", growth=.35,
        business="Säljer bland annat kroppskameror, TASER och molnsystem för bevismaterial och säkerhetsarbete.",
        opportunity="Fler anslutna enheter och mjukvarutjänster kan öka försäljningen per kund, om offentliga budgetar och regler tillåter.",
        competition="Integration mellan utrustning och programvara kan ge kundnytta, men bolagets egna plattformspåståenden verifierar ingen vallgrav.",
        milestone="Följ abonnemangsintäkter, marginaler och kassaflöde när nya tjänster införs.",
        risk="Offentliga upphandlingar, integritetsfrågor och ett högt pris på förväntad tillväxt kan begränsa avkastningen.",
        fact="Bolaget rapporterade 35 % omsättningstillväxt; kvartalets fria kassaflöde var svagt negativt.",
        url="https://www.sec.gov/Archives/edgar/data/1069183/000162828026053363/axon-20260805xex991.htm"),
}

# Exposure identifies what to research; these conditional scenarios do not
# verify market-share gains, a moat or an automatic buy decision.
INDUSTRY_CASES = [
    (("semiconductor", "electronic components", "communication equipment"), "Halvledare och datainfrastruktur",
     "utvecklar kretsar eller elektronik för databehandling och kommunikation",
     "Mer databehandling och snabbare kommunikation kan öka efterfrågan. Följ faktisk produktförsäljning och kundernas investeringar.",
     "Konkurrerande arkitekturer, kundernas egna kretsar och tekniska generationsskiften kan pressa marginalerna.",
     "Följ produktmix, kundkoncentration, bruttomarginal och om tillväxten beror på volym eller priser."),
    (("software", "information technology services", "internet content"), "Programvara och digitala tjänster",
     "säljer programvara eller digitala tjänster",
     "Digitalisering och automatisering kan ge fler kunder eller högre användning. Följ återkommande intäkter och kundnytta som kunder faktiskt betalar för.",
     "AI kan både skapa nya tjänster och göra befintliga funktioner billigare att kopiera. Kundbehållning och försäljningskostnad avgör om tillväxten håller.",
     "Följ kundbehållning, intäkt per kund, aktiebaserad ersättning och kassaflöde per aktie."),
    (("medical devices", "medical instruments", "diagnostics", "biotechnology"), "Medicinsk teknik och behandling",
     "utvecklar medicinsk teknik, diagnostik eller behandlingar",
     "Nya behandlingar och bättre diagnostik kan möta medicinska behov, om studier, godkännanden och ersättningssystem stödjer användningen.",
     "Kliniska misslyckanden, konkurrerande behandlingar och utebliven ersättning kan stoppa kommersialiseringen.",
     "Följ kliniska resultat, regulatoriska beslut, faktisk försäljning och kassa fram till nästa milstolpe."),
    (("aerospace", "defense"), "Flyg, rymd och säkerhet",
     "levererar teknik eller system till flyg-, rymd- eller säkerhetsmarknader",
     "Nya system och ökade säkerhetsbehov kan skapa efterfrågan. Order måste bli leveranser med fungerande marginaler.",
     "Upphandlingsbeslut, fasta kontraktspriser, förseningar och tekniska fel kan göra en växande orderbok olönsam.",
     "Följ orderingång, leveransförmåga, utvecklingskostnader och kassaflöde."),
    (("solar", "electrical equipment", "specialty industrial machinery"), "Energi och industriell teknik",
     "levererar teknik för energisystem eller industriella processer",
     "Elektrifiering, energieffektivisering och automatisering kan driva investeringar, om kundernas projekt får ekonomi och finansiering.",
     "Överkapacitet, prispress, ändrade stödregler och uppskjutna kundprojekt kan ge tillväxt utan lönsamhet.",
     "Följ orderkvalitet, kapacitetsutnyttjande, serviceintäkter och avkastning på investerat kapital."),
]


def discovery_context(row, report):
    """Describe exposure and maturity before comparing financial growth."""
    industry = str(row.get("Bransch") or "").lower()
    name = str(row.get("Namn") or row.get("Ticker") or "Bolaget")
    matched = next((case for case in INDUSTRY_CASES if any(key in industry for key in case[0])), None)
    cyclical = any(key in industry for key in ("gold", "silver", "precious metal", "oil & gas", "coal", "steel", "marine shipping", "copper", "aluminum"))
    cap = _number(row.get("_Raw marketCap"))
    # Compare only verified USD quotes. A local-currency cap must not be treated
    # as dollars; unknown size is disclosed instead of assumed small.
    established = str(row.get("Valuta") or "").upper() == "USD" and cap is not None and cap >= 100e9
    fit = 2 if report or matched else 1
    category = "Framtidsinriktad verksamhet" if fit == 2 else "Tillväxtuppslag · verksamhetsgranskning återstår"
    if cyclical:
        fit, category = 0, "Cykliskt bolag · tillväxten kan bero på råvarupriser"
    if established:
        fit, category = 0, "Etablerat megabolag · lägre prioritet i upptäcktslistan"
    if matched:
        _, theme, business, opportunity, competition, milestone = matched
        return dict(fit=fit, category=category, theme=theme, business=f"{name} {business}. Branschklassning enligt bolagsdatakällan; produktbeskrivningen kan läsas nedan.", opportunity=opportunity, competition=competition, milestone=milestone)
    return dict(fit=fit, category=category, theme=row.get("Bransch") or "Verksamhet behöver granskas",
                business=f"{name}: bolagets verksamhet behöver granskas i källbeskrivningen nedan.",
                opportunity="Tillväxtsökningen visar ett uppslag. Verifiera vilka produkter och kundbehov som kan driva fortsatt tillväxt; hög historisk tillväxt visar inte framtida efterfrågan.",
                competition="Konkurrenter, prissättningsmakt och kundbehållning är ännu inte granskade. Ingen verifierad vallgrav tillskrivs bolaget.",
                milestone="Kontrollera nästa rapports segmenttillväxt, kundutveckling och kassaflöde.")


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _age(value, now):
    try:
        stamp = pd.Timestamp(value)
        if pd.isna(stamp):
            return None
        if stamp.tzinfo is None:
            stamp = stamp.tz_localize("UTC")
        return (pd.Timestamp(now) - stamp).total_seconds() / 86400
    except (ValueError, TypeError):
        return None


def screen_growth(regions):
    """Two regional screens, no earnings/profitability gate or microcap limit."""
    import yfinance as yf

    query = yf.EquityQuery("and", [
        yf.EquityQuery("or", [yf.EquityQuery("eq", ["region", r]) for r in regions]),
        yf.EquityQuery("gte", ["quarterlyrevenuegrowth.quarterly", 15]),
        yf.EquityQuery("gte", ["intradaymarketcap", 100_000_000]),
    ])
    # yfinance shares its data session across Tickers and screen(). Do not replace
    # it with a temporary/closed session and break the main app's quote requests.
    response = yf.screen(query, size=24, sortField="eodvolume", sortAsc=False)
    return (response or {}).get("quotes", [])


def collect_future_pool(fetch_fundamentals, screen=screen_growth, now=None):
    """Bounded acquisition. Failures retain dated research, never invented metrics."""
    now = now or datetime.now(timezone.utc)
    candidates = {ticker: {"Ticker": ticker, "Namn": p["name"], "Upptäckt via": "Rapportbaserat bevakningsurval"} for ticker, p in REPORTS.items()}
    errors = []
    hits = 0
    for label, regions in [("Nordamerika", ("us", "ca")), ("Europa", ("gb", "de", "fr", "se", "no", "dk", "fi", "nl"))]:
        try:
            quotes = screen(regions)
            if not quotes:
                errors.append(f"{label}: tillväxtsökningen gav inga träffar.")
            for quote in quotes[:24]:
                symbol = str(quote.get("symbol") or "").strip().upper()
                if not re.fullmatch(r"[A-Z0-9^][A-Z0-9.\-^=]{0,24}", symbol):
                    continue
                if quote.get("quoteType", "EQUITY") != "EQUITY":
                    continue
                hits += 1
                candidates.setdefault(symbol, {"Ticker": symbol, "Namn": quote.get("shortName") or quote.get("longName") or symbol, "Upptäckt via": f"Yahoo tillväxtsökning · {label}"})
        except Exception as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            detail = f"HTTP {int(status)}" if isinstance(status, int) else type(exc).__name__
            errors.append(f"{label}: tillväxtsökningen kunde inte hämtas ({detail}).")
    rows = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_fundamentals, ticker): ticker for ticker in candidates}
        for future in as_completed(futures):
            ticker = futures[future]
            row = candidates[ticker].copy()
            try:
                payload = future.result()
                row.update({k: v for k, v in payload.items() if k != "Ticker"})
                if row.get("Fundamental source status") in {"ERROR", "CIRCUIT_OPEN", "DEGRADED"}:
                    errors.append(f"{ticker}: bolagsdata är ofullständiga eller använder reservkälla.")
            except Exception as exc:
                errors.append(f"{ticker}: bolagsdata saknas ({type(exc).__name__}).")
            row["Ticker"] = ticker
            rows.append(assess_future_candidate(row, now))
    return pd.DataFrame(rows), {"candidates": len(candidates), "screen_hits": hits, "errors": errors, "fetched_at": now.isoformat()}


def assess_future_candidate(row, now=None):
    now = now or datetime.now(timezone.utc)
    out = dict(row)
    ticker = str(row.get("Ticker") or "").strip().upper()
    out["Ticker"] = ticker
    report = REPORTS.get(ticker, {})
    context = discovery_context(row, report)
    report_age = _age(report.get("date"), now)
    report_fresh = report_age is not None and 0 <= report_age <= 120
    live_age = _age(row.get("Fundamental hämtad"), now)
    live_fresh = live_age is not None and 0 <= live_age <= 3 and row.get("Fundamental source status") not in {"ERROR", "CIRCUIT_OPEN"}
    live_growth = _number(row.get("Omsättningstillväxt")) if live_fresh else None
    # A newer declining business must not be rescued by an older growth report.
    growth = live_growth if live_growth is not None else report.get("growth") if report_fresh else None
    margin = _number(row.get("Vinstmarginal")) if live_fresh else None
    fcf = _number(row.get("FCF-yield")) if live_fresh else None
    debt = _number(row.get("Skuld/eget kapital")) if live_fresh else None
    pe = _number(row.get("P/E")) if live_fresh else None
    ev = _number(row.get("EV/EBITDA")) if live_fresh else None
    flags = []
    if growth is None:
        flags.append("Aktuell tillväxt är inte verifierad")
    elif growth <= 0:
        flags.append("Senaste tillgängliga omsättningstillväxt är inte positiv")
    if margin is None:
        flags.append("Lönsamhet saknas i aktuella bolagsdata")
    elif margin < 0:
        flags.append("Förlust: finansiering och utspädning behöver granskas")
    if fcf is None:
        flags.append("Aktuellt fritt kassaflöde saknas")
    elif fcf <= 0:
        flags.append("Fritt kassaflöde är inte positivt")
    if debt is None or debt < 0:
        flags.append("Balansräkning och finansieringsutrymme behöver granskas")
    elif debt > 200:
        flags.append("Hög skuld i förhållande till eget kapital")
    if not ((pe is not None and pe > 0) or (ev is not None and ev > 0)):
        flags.append("Värderingsstöd saknas")
    elif (pe or 0) > 50 or (ev or 0) > 35:
        flags.append("Hög vinstmultipel: mycket tillväxt kan redan vara inprisad")
    if report and not report_fresh:
        flags.append("Rapportunderlaget är äldre än 120 dagar eller har ogiltigt datum")
    source = "Yahoo bolagsdata" if live_growth is not None else f"Bolagets {report.get('period', '')}, publicerad {report.get('date', '')}" if growth is not None else "Saknas"
    out.update({
        "Namn": report.get("name") or row.get("Namn") or ticker,
        "Framtid kategori": context["category"], "_future_fit": context["fit"],
        "Framtid tema": report.get("theme") or context["theme"],
        "Framtid verksamhet": report.get("business") or context["business"],
        "Framtid källbeskrivning": str(row.get("Verksamhetsbeskrivning") or "")[:1800],
        "Framtid möjlighet": report.get("opportunity") or context["opportunity"],
        "Framtid konkurrens": report.get("competition") or context["competition"],
        "Framtid milstolpe": report.get("milestone") or context["milestone"],
        "Framtid risk": report.get("risk") or "Tillväxten kan vara tillfällig, förvärvsdriven eller redan inprisad. Finansiering och konkurrens måste granskas.",
        "Framtid rapportfakta": report.get("fact", "Bolagsspecifik rapportgranskning återstår."),
        "Framtid rapportdatum": report.get("date", ""), "Framtid rapportperiod": report.get("period", ""),
        "Framtid rapportkälla": report.get("url", ""), "Framtid tillväxt": growth,
        "Framtid tillväxtkälla": source, "Framtid hinder": "; ".join(flags),
        "Framtid köpstatus": "BEVAKA · köpläge inte prövat",
        "Framtid underlag": "Rapport och bolagsdata" if report_fresh and live_fresh else "Daterad rapport · bolagsdata begränsade" if report_fresh else "Bolagsdata · rapportgranskning återstår" if live_fresh else "Otillräckligt aktuellt underlag",
        # Ordinal ordering, not an alternative Borsify score. Missing is never neutral.
        "_future_growth_confirmed": growth is not None and growth > 0,
        "_future_economics": int(margin is not None and margin > 0) + int(fcf is not None and fcf > 0),
        "_future_growth": min(growth, 1.0) if growth is not None else -math.inf,
        "_future_risks": len(flags),
    })
    return out


def select_future_companies(frame, limit=5):
    if frame is None or frame.empty:
        return pd.DataFrame()
    out = frame.copy()
    out["Ticker"] = out["Ticker"].astype(str).str.strip().str.upper()
    out = out[out["Ticker"].ne("") & out["Ticker"].ne("NAN")]
    out = out.sort_values(["_future_fit", "_future_growth_confirmed", "_future_economics", "_future_risks", "_future_growth", "Ticker"], ascending=[False, False, False, True, False, True], kind="stable")
    return out.drop_duplicates("Ticker").head(max(0, int(limit))).reset_index(drop=True)
