from __future__ import annotations

import re
import ssl
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class IdeaSource:
    name: str
    kind: str
    url: str
    category: str = "Brett flöde"
    weight: float = 1.0


def _google_news_query(query: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + urllib.parse.quote(query)
        + "&hl=sv&gl=SE&ceid=SE:sv"
    )


# Externa källor används bara som radar för uppslag. De ändrar aldrig Borsify Score.
# Direkt RSS används där en stabil publik feed finns; i övrigt används Google News RSS
# för att undvika skör sid-scraping av respektive mediesajt.
DEFAULT_SOURCES = [
    IdeaSource(
        "EFN · direkt RSS",
        "media",
        "https://efn.se/rss/infront",
        category="Ekonomimedia",
        weight=1.15,
    ),
    IdeaSource(
        "Svensk ekonomimedia · brett",
        "media",
        _google_news_query(
            '(aktie OR börs OR rapport OR utdelning OR riktkurs) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:dagensps.se OR site:borsvarlden.com)'
        ),
        category="Ekonomimedia",
        weight=1.0,
    ),
    IdeaSource(
        "Analyser & rekommendationer",
        "media",
        _google_news_query(
            '(aktie OR bolag) (analys OR rekommendation OR riktkurs OR köprekommendation OR säljrekommendation) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:borsvarlden.com)'
        ),
        category="Analys & rekommendation",
        weight=1.05,
    ),
    IdeaSource(
        "Rapporter & bolagshändelser",
        "media",
        _google_news_query(
            '(rapport OR vinstvarning OR utdelning OR insynsköp OR order OR förvärv OR emission) '
            '(site:di.se OR site:placera.se OR site:affarsvarlden.se OR site:borskollen.se '
            'OR site:efn.se OR site:privataaffarer.se OR site:borsvarlden.com)'
        ),
        category="Bolagshändelse",
        weight=1.1,
    ),
    IdeaSource(
        "Internationell ekonomimedia · brett",
        "media",
        _google_news_query(
            '(stock OR shares OR earnings OR dividend OR analyst OR target price) '
            '(site:reuters.com OR site:cnbc.com OR site:marketwatch.com OR site:finance.yahoo.com OR site:investing.com)'
        ),
        category="Internationell ekonomimedia",
        weight=1.0,
    ),
    IdeaSource(
        "Internationella analyser & bolagshändelser",
        "media",
        _google_news_query(
            '(earnings OR guidance OR upgrade OR downgrade OR dividend OR acquisition OR buyback) '
            '(site:reuters.com OR site:cnbc.com OR site:marketwatch.com OR site:finance.yahoo.com)'
        ),
        category="Internationell analys & bolagshändelse",
        weight=1.05,
    ),
    IdeaSource(
        "Forum · Reddit stocks",
        "forum",
        "https://www.reddit.com/r/stocks/new/.rss",
        category="Forum · internationellt",
        weight=0.55,
    ),
    IdeaSource(
        "Forum · Reddit Aktiemarknaden",
        "forum",
        "https://www.reddit.com/r/Aktiemarknaden/new/.rss",
        category="Forum",
        weight=0.65,
    ),
    IdeaSource(
        "Forum · Reddit ISKbets",
        "forum",
        "https://www.reddit.com/r/ISKbets/new/.rss",
        category="Forum · hög spekulationsrisk",
        weight=0.45,
    ),
]




EVENT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Vinstvarning / tydlig försämring", (
        "vinstvarning", "vinstvarnar", "profit warning", "cuts guidance", "lowered guidance", "sänker prognos",
        "sanker prognos", "svagare än väntat", "svagare an vantat", "missar förvänt", "misses estimates",
    )),
    ("Rapport / resultat", (
        "rapport", "delårsrapport", "delarsrapport", "bokslut", "årsrapport", "arsrapport",
        "earnings", "results", "quarter", "q1", "q2", "q3", "q4", "ebit", "ebita",
    )),
    ("Prognos / guidance", (
        "prognos", "utsikter", "guidance", "outlook", "höjer prognos", "hojer prognos",
        "raises guidance", "guides",
    )),
    ("Analys / riktkurs", (
        "riktkurs", "köprekommendation", "koprekommendation", "säljrekommendation", "saljrekommendation",
        "rekommendation", "analys", "upgrade", "downgrade", "price target", "target price",
        "buy rating", "sell rating", "overweight", "underweight",
    )),
    ("Insiderhandel", (
        "insynsköp", "insynskop", "insiderköp", "insiderkop", "insider purchase", "insider buying",
        "insynsförsälj", "insynsforsalj", "insider sale",
    )),
    ("Order / kontrakt", (
        "stororder", "order värd", "order vard", "order value", "kontrakt", "contract",
        "ramavtal", "framework agreement", "upphandling",
    )),
    ("Förvärv / fusion / bud", (
        "förvärv", "forvarv", "acquisition", "acquire", "köper", "koper", "takeover",
        "bud på", "bud pa", "merger", "fusion", "m&a",
    )),
    ("Utdelning / återköp", (
        "utdelning", "dividend", "återköp", "aterkop", "buyback", "share repurchase",
    )),
    ("Emission / finansiering", (
        "nyemission", "företrädesemission", "foretradesemission", "emission", "rights issue",
        "share issue", "kapitalanskaff", "finansiering", "refinancing",
    )),
    ("Ledning / styrelse", (
        "vd avgår", "vd avgar", "ny vd", "ceo resign", "new ceo", "styrelse", "board",
        "ordförande", "ordforande", "chairman",
    )),
    ("Regulatoriskt / juridiskt", (
        "myndighet", "finansinspektionen", "konkurrensverket", "domstol", "stämning", "stamning",
        "lawsuit", "regulator", "investigation", "böter", "boter", "fine", "approval", "godkännande", "godkannande",
    )),
    ("Produkt / lansering", (
        "lanserar", "lansering", "launch", "new product", "produkt", "godkänd produkt", "approved product",
    )),
    ("Kursrörelse / marknadsreaktion", (
        "rusar", "rasar", "stiger", "faller", "lyfter", "sjunker", "shares jump", "shares fall",
        "stock jumps", "stock falls",
    )),
]

EVENT_PRIORITY = {name: i for i, (name, _) in enumerate(EVENT_RULES)}
EVENT_PRIORITY.update({"Forumdiskussion": 90, "Övrigt / oklart": 99})


def classify_event(title: str, summary: str = "", kind: str = "media") -> list[str]:
    """Klassificerar vad rubriken sannolikt handlar om – inte om nyheten är bra eller dålig.

    Klassningen är avsiktligt enkel och deterministisk. Den ska hjälpa användaren att förstå
    *varför* ett bolag syns i flödet, men originalkällan måste läsas för att verifiera händelsen.
    """
    hay = _normalize(f"{title} {summary}")
    hits: list[str] = []
    for label, terms in EVENT_RULES:
        if any(_normalize(term) in hay for term in terms):
            hits.append(label)
    if not hits:
        hits.append("Forumdiskussion" if kind == "forum" else "Övrigt / oklart")
    return sorted(set(hits), key=lambda x: EVENT_PRIORITY.get(x, 99))


def event_explanation(event_types: list[str]) -> str:
    if not event_types:
        return "Borsify kunde inte avgöra vad uppmärksamheten gäller enbart från rubrikerna."
    main = event_types[0]
    explanations = {
        "Vinstvarning / tydlig försämring": "Rubrikerna tyder på en vinstvarning eller tydlig försämring. Det är en riskhändelse som bör läsas i original innan nyckeltalen tolkas.",
        "Rapport / resultat": "Uppmärksamheten verkar främst bero på en rapport eller nya resultatsiffror. Kontrollera om vinsten, omsättningen och utsikterna faktiskt förändrats.",
        "Prognos / guidance": "Bolagets framtidsutsikter eller prognos verkar stå i centrum. Jämför det nya beskedet med tidigare förväntningar.",
        "Analys / riktkurs": "En eller flera externa analyser eller riktkurser verkar driva uppmärksamheten. Det är en åsikt från marknaden, inte ny fundamental fakta i sig.",
        "Insiderhandel": "Uppmärksamheten verkar gälla köp eller försäljning från personer nära bolaget. Det kan vara intressant, men ska inte ensamt styra ett investeringsbeslut.",
        "Order / kontrakt": "Bolaget verkar ha fått eller diskuterats kring en order eller ett kontrakt. Kontrollera storleken i förhållande till bolagets normala omsättning.",
        "Förvärv / fusion / bud": "Uppmärksamheten verkar gälla ett förvärv, bud eller en fusion. Sådana händelser kan ändra både tillväxtmöjlighet och risk snabbt.",
        "Utdelning / återköp": "Utdelning eller återköp verkar vara orsaken till uppmärksamheten. Kontrollera om utbetalningen är hållbar och hur den finansieras.",
        "Emission / finansiering": "Bolaget verkar ta in eller omfördela kapital. Kontrollera utspädning, villkor och varför pengarna behövs.",
        "Ledning / styrelse": "Förändringar i ledning eller styrelse verkar vara nyheten. Bedöm om förändringen påverkar bolagets strategi eller genomförandeförmåga.",
        "Regulatoriskt / juridiskt": "Myndighets-, godkännande- eller juridiska frågor verkar ligga bakom uppmärksamheten. Här är originalkällan särskilt viktig.",
        "Produkt / lansering": "En produkt, tjänst eller lansering verkar vara i fokus. Kontrollera om den är ekonomiskt betydelsefull för bolaget.",
        "Kursrörelse / marknadsreaktion": "Rubrikerna beskriver främst en stor kursrörelse. Borsify försöker därför hitta den bakomliggande orsaken i övriga rubriker innan rörelsen tolkas.",
        "Forumdiskussion": "Bolaget diskuteras i forum, men någon tydlig bolagshändelse går inte att fastställa från rubriken.",
        "Övrigt / oklart": "Borsify ser uppmärksamhet men kan inte säkert avgöra orsaken från rubrikerna. Läs originalkällan innan du drar slutsatser.",
    }
    return explanations.get(main, explanations["Övrigt / oklart"])


def _clean_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _parse_date(value: str | None) -> pd.Timestamp:
    if not value:
        return pd.NaT
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return pd.Timestamp(dt)
    except Exception:
        try:
            ts = pd.Timestamp(value)
            return ts.tz_localize(None) if ts.tzinfo is not None else ts
        except Exception:
            return pd.NaT


def _fetch_xml(url: str, timeout: int = 8) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Borsify/2.18 (+https://borsify.se; public-feed-reader)",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as response:
        return response.read()


def _publisher_from_title(title: str, fallback: str) -> str:
    # Google News brukar lägga publicisten sist i rubriken: "Rubrik - EFN".
    if " - " in title:
        suffix = title.rsplit(" - ", 1)[-1].strip()
        if 2 <= len(suffix) <= 40:
            return suffix
    return fallback


def parse_feed(xml_bytes: bytes, source: IdeaSource, max_items: int = 40) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    rows: list[dict] = []

    for item in root.findall(".//item")[:max_items]:
        title = _clean_html(item.findtext("title") or "")
        summary = _clean_html(item.findtext("description") or "")
        link = (item.findtext("link") or "").strip()
        published = _parse_date(item.findtext("pubDate"))
        xml_publisher = _clean_html(item.findtext("source") or "")
        publisher = xml_publisher or _publisher_from_title(title, source.name)
        rows.append({
            "source": source.name,
            "publisher": publisher,
            "kind": source.kind,
            "category": source.category,
            "source_weight": source.weight,
            "title": title,
            "summary": summary,
            "link": link,
            "published": published,
        })

    if rows:
        return rows

    ns = {"a": "http://www.w3.org/2005/Atom"}
    for entry in root.findall(".//a:entry", ns)[:max_items]:
        title = _clean_html(entry.findtext("a:title", default="", namespaces=ns))
        summary = _clean_html(
            entry.findtext("a:summary", default="", namespaces=ns)
            or entry.findtext("a:content", default="", namespaces=ns)
        )
        link_el = entry.find("a:link", ns)
        link = link_el.attrib.get("href", "") if link_el is not None else ""
        published = _parse_date(
            entry.findtext("a:published", default="", namespaces=ns)
            or entry.findtext("a:updated", default="", namespaces=ns)
        )
        rows.append({
            "source": source.name,
            "publisher": source.name,
            "kind": source.kind,
            "category": source.category,
            "source_weight": source.weight,
            "title": title,
            "summary": summary,
            "link": link,
            "published": published,
        })
    return rows


def fetch_public_idea_flow(
    sources: Iterable[IdeaSource] = DEFAULT_SOURCES,
    max_items_per_source: int = 40,
) -> tuple[pd.DataFrame, list[str]]:
    rows: list[dict] = []
    errors: list[str] = []
    for source in sources:
        try:
            rows.extend(parse_feed(_fetch_xml(source.url), source, max_items=max_items_per_source))
        except Exception as exc:
            errors.append(f"{source.name}: {type(exc).__name__}")
    columns = ["source", "publisher", "kind", "category", "source_weight", "title", "summary", "link", "published"]
    if not rows:
        return pd.DataFrame(columns=columns), errors
    frame = pd.DataFrame(rows)
    frame["published"] = pd.to_datetime(frame["published"], errors="coerce")
    frame = frame.drop_duplicates(subset=["title", "link"], keep="first")
    return frame.sort_values("published", ascending=False, na_position="last").reset_index(drop=True), errors


def _normalize(text: str) -> str:
    text = (text or "").lower().replace("&", " och ")
    text = re.sub(r"[^a-z0-9åäö]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _aliases(name: str, ticker: str) -> list[str]:
    base = re.sub(r"\.ST$", "", ticker or "", flags=re.I)
    base = re.sub(r"-[A-Z]$", "", base, flags=re.I)
    clean_name = re.sub(r"\b(ab|publ|class|ser\.?\s*[ab]|aktiebolag)\b", " ", name or "", flags=re.I)
    candidates = [_normalize(clean_name), _normalize(base)]
    tokens = _normalize(clean_name).split()
    if tokens and len(tokens[0]) >= 4:
        candidates.append(tokens[0])
    return sorted({x for x in candidates if len(x) >= 3}, key=len, reverse=True)


def _mentioned(text: str, aliases: list[str]) -> bool:
    hay = f" {_normalize(text)} "
    return any(f" {alias} " in hay for alias in aliases)


def map_mentions(feed: pd.DataFrame, stocks: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "Ticker", "Namn", "Antal omnämnanden", "Källor", "Forum", "Media", "Senast nämnd",
        "Rubriker", "Mediekällor", "Forumkällor", "Kategorier", "Viktade omnämnanden",
        "Omnämnanden 24h", "Omnämnanden 7d", "Mediepuls", "Huvudhändelse", "Händelsetyper", "Händelseförklaring",
    ]
    if feed.empty or stocks.empty:
        return pd.DataFrame(columns=columns)
    stock_rows = []
    for _, stock in stocks.iterrows():
        ticker = str(stock.get("Ticker", ""))
        name = str(stock.get("Namn", ticker))
        aliases = _aliases(name, ticker)
        matches = []
        for _, item in feed.iterrows():
            text = f"{item.get('title','')} {item.get('summary','')}"
            if _mentioned(text, aliases):
                matches.append(item)
        if not matches:
            continue
        m = pd.DataFrame(matches)
        published = pd.to_datetime(m["published"], errors="coerce")
        latest = published.max() if published.notna().any() else pd.NaT
        publisher_series = m.get("publisher", m["source"]).fillna(m["source"]).astype(str)
        media_mask = m["kind"].eq("media")
        forum_mask = m["kind"].eq("forum")
        headlines = []
        for _, r in m.sort_values("published", ascending=False, na_position="last").head(6).iterrows():
            event_types = classify_event(str(r.get("title", "")), str(r.get("summary", "")), str(r.get("kind", "media")))
            headlines.append({
                "title": str(r.get("title", "")),
                "source": str(r.get("publisher", r.get("source", ""))),
                "feed": str(r.get("source", "")),
                "category": str(r.get("category", "")),
                "kind": str(r.get("kind", "")),
                "event_types": event_types,
                "link": str(r.get("link", "")),
                "published": r.get("published"),
            })
        weights = pd.to_numeric(m.get("source_weight", 1.0), errors="coerce").fillna(1.0)
        now = pd.Timestamp.utcnow().tz_localize(None)
        ages = (now - published).dt.total_seconds() / 86400.0
        mentions_24h = int(((ages >= 0) & (ages <= 1)).sum())
        mentions_7d = int(((ages >= 0) & (ages <= 7)).sum())
        older_window = max(mentions_7d - mentions_24h, 0)
        older_daily = older_window / 6.0
        if mentions_24h >= 3 and mentions_24h >= max(older_daily * 2.0, 2.0):
            pulse = "Ökad uppmärksamhet"
        elif mentions_24h >= 2:
            pulse = "Aktivt just nu"
        elif mentions_24h == 1:
            pulse = "Nytt omnämnande"
        else:
            pulse = "Ingen tydlig ny puls"

        all_event_types: list[str] = []
        for h in headlines:
            all_event_types.extend(h.get("event_types", []))
        # Välj den mest konkreta/angelägna händelsetypen enligt den fasta prioriteringen.
        event_types = sorted(set(all_event_types), key=lambda x: EVENT_PRIORITY.get(x, 99))
        main_event = event_types[0] if event_types else ("Forumdiskussion" if forum_mask.all() else "Övrigt / oklart")
        stock_rows.append({
            "Ticker": ticker,
            "Namn": name,
            "Antal omnämnanden": int(len(m)),
            "Källor": int(publisher_series.nunique()),
            "Forum": int(forum_mask.sum()),
            "Media": int(media_mask.sum()),
            "Senast nämnd": latest,
            "Rubriker": headlines,
            "Mediekällor": int(publisher_series[media_mask].nunique()),
            "Forumkällor": int(publisher_series[forum_mask].nunique()),
            "Kategorier": int(m.get("category", pd.Series(dtype=str)).nunique()),
            "Viktade omnämnanden": float(weights.sum()),
            "Omnämnanden 24h": mentions_24h,
            "Omnämnanden 7d": mentions_7d,
            "Mediepuls": pulse,
            "Huvudhändelse": main_event,
            "Händelsetyper": event_types,
            "Händelseförklaring": event_explanation(event_types),
        })
    return pd.DataFrame(stock_rows)


def discovery_strength(row: pd.Series, now: pd.Timestamp | None = None) -> float:
    """Mäter bredd + aktualitet i externa uppslag, inte hur bra investeringen är."""
    now = now or pd.Timestamp.utcnow().tz_localize(None)
    weighted_mentions = float(row.get("Viktade omnämnanden", row.get("Antal omnämnanden", 0)) or 0)
    publishers = float(row.get("Källor", 0) or 0)
    media_publishers = float(row.get("Mediekällor", 0) or 0)
    latest = pd.to_datetime(row.get("Senast nämnd"), errors="coerce")
    if pd.isna(latest):
        recency = 4.0
    else:
        age_days = max((now - pd.Timestamp(latest).tz_localize(None)).total_seconds() / 86400.0, 0.0)
        recency = max(0.0, 24.0 - min(age_days, 12.0) * 2.0)
    score = min(30.0, weighted_mentions * 6.0) + min(36.0, publishers * 12.0) + recency
    if media_publishers >= 2:
        score += 10.0
    # Forum kan hitta idéer snabbt, men många foruminlägg ska inte ensamma ge "stark" upptäckt.
    if media_publishers == 0:
        score = min(score, 68.0)
    return round(min(score, 100.0), 1)


def combination_signal(row: pd.Series) -> tuple[str, str, float]:
    """Prioriterar externa uppslag som sammanfaller med stark intern data.

    Detta är inte en ny investeringsscore. Extern uppmärksamhet får aldrig ändra
    Borsify Score, INVEST, SWING eller REVERSAL. Prioriteten används bara för att
    sortera vilka redan externt upptäckta case som är mest värda att läsa vidare om.
    """
    def n(key: str) -> float:
        value = pd.to_numeric(row.get(key), errors="coerce")
        return float(value) if pd.notna(value) else np.nan

    b = n("Borsify Score")
    invest = n("INVEST Score")
    swing = n("SWING Score")
    reversal = n("REVERSAL Score")
    quality = n("Kvalitet")
    valuation = n("Värdering")
    risk = n("Risk")
    discovery = n("Upptäcktsstyrka")
    media_sources = n("Mediekällor")
    mentions24 = n("Omnämnanden 24h")
    pulse = str(row.get("Mediepuls", ""))

    internal = b if np.isfinite(b) else 0.0
    external = discovery if np.isfinite(discovery) else 0.0
    # Endast en kö-prioritering för redan upptäckta idéer, aldrig en ändring av Borsify Score.
    queue_priority = round(min(100.0, max(0.0, 0.72 * internal + 0.28 * external)), 1)

    solid_risk = (not np.isfinite(risk)) or risk >= 50
    solid_quality = np.isfinite(quality) and quality >= 60
    reasonable_price = np.isfinite(valuation) and valuation >= 55
    real_media_breadth = np.isfinite(media_sources) and media_sources >= 2
    pulse_up = pulse in {"Ökad uppmärksamhet", "Aktivt just nu"} or (np.isfinite(mentions24) and mentions24 >= 2)

    if np.isfinite(b) and b >= 72 and solid_quality and reasonable_price and solid_risk and pulse_up and real_media_breadth:
        return (
            "Ovanligt intressant kombination",
            "Flera oberoende källor har börjat uppmärksamma bolaget samtidigt som Borsifys egen kontroll visar bra kvalitet, rimlig värdering och acceptabel risk. Det gör caset värt att läsa vidare om – men medieintresset är inte ett köpbevis.",
            queue_priority,
        )
    if np.isfinite(invest) and invest >= 70 and solid_quality and solid_risk and pulse_up:
        return (
            "Kvalitetsbolag i fokus",
            "Bolaget ser långsiktigt intressant ut i Borsifys data och får samtidigt mer extern uppmärksamhet. Kontrollera vad som utlöst intresset och om nyheten förändrar bolagets långsiktiga förutsättningar.",
            queue_priority,
        )
    if np.isfinite(reversal) and reversal >= 72 and solid_risk and pulse == "Ökad uppmärksamhet":
        return (
            "Möjlig återhämtningsidé",
            "Aktien har ett starkt återhämtningsläge enligt Borsifys prisdata och uppmärksamheten har ökat. Det kan vara ett intressant uppslag efter ett fall, men kontrollera först varför aktien föll.",
            queue_priority,
        )
    if np.isfinite(swing) and swing >= 72 and solid_risk and pulse_up:
        return (
            "Kortsiktigt läge i fokus",
            "Borsifys kortsiktiga signal är stark samtidigt som aktien syns mer i externa källor. Det är ett läge att analysera vidare, inte en automatisk köpsignal.",
            queue_priority,
        )
    if np.isfinite(b) and b >= 60 and external >= 45:
        return (
            "Värt en närmare titt",
            "Både Borsifys grunddata och den externa uppmärksamheten är tillräckligt intressanta för att motivera en närmare kontroll, men kombinationen är inte stark nog för en tydligare flagga.",
            queue_priority,
        )
    return (
        "Ingen särskild kombination",
        "Det finns ett externt uppslag, men Borsify ser ännu ingen ovanligt stark kombination av uppmärksamhet och egna nyckeltal.",
        queue_priority,
    )



def case_impact_assessment(row: pd.Series) -> tuple[str, str, int]:
    """Bedömer hur mycket en extern händelse *kan* påverka investeringscaset.

    Funktionen tolkar inte om en nyhet är positiv eller negativ när rubriken inte räcker
    för det. Den skiljer i stället mellan händelser som ofta kan ändra fundamenta och
    sådant som främst är marknadsbrus eller andrahandsåsikter.
    """
    event = str(row.get("Huvudhändelse", "Övrigt / oklart"))
    event_types = row.get("Händelsetyper") or []
    if not isinstance(event_types, (list, tuple, set)):
        event_types = [str(event_types)]
    event_set = {str(x) for x in event_types}

    def n(key: str) -> float:
        v = pd.to_numeric(row.get(key), errors="coerce")
        return float(v) if pd.notna(v) else np.nan

    risk = n("Risk")
    quality = n("Kvalitet")
    debt = n("Skuld/eget kapital")

    if "Vinstvarning / tydlig försämring" in event_set or event == "Vinstvarning / tydlig försämring":
        return (
            "Ny risk – kontrollera direkt",
            "En vinstvarning eller tydlig försämring kan ändra bolagets värde snabbt. Läs originalkällan och kontrollera vad som ändrats i vinst, omsättning och framtidsutsikter innan äldre nyckeltal får väga tungt.",
            3,
        )

    if event in {"Rapport / resultat", "Prognos / guidance", "Förvärv / fusion / bud", "Regulatoriskt / juridiskt"}:
        return (
            "Kan ändra investeringscaset",
            "Det här är en typ av händelse som kan påverka bolagets framtida vinst, risk eller värdering. Borsify väntar därför med att kalla den positiv eller negativ tills de faktiska siffrorna eller villkoren är verifierade.",
            3,
        )

    if event == "Emission / finansiering":
        extra = ""
        if (np.isfinite(risk) and risk < 50) or (np.isfinite(debt) and debt > 150):
            extra = " Bolaget har dessutom redan en svagare riskbild i Borsifys data, så finansieringen är extra viktig att förstå."
        return (
            "Kan ändra riskbilden",
            "En emission eller ny finansiering kan ge bolaget mer kapital men också späda ut befintliga ägare eller signalera finansieringsbehov. Kontrollera villkor, belopp och varför pengarna behövs." + extra,
            3,
        )

    if event in {"Order / kontrakt", "Produkt / lansering", "Insiderhandel", "Utdelning / återköp", "Ledning / styrelse"}:
        context = ""
        if event == "Order / kontrakt":
            context = " Storleken i relation till bolagets årsomsättning avgör om ordern verkligen är betydelsefull."
        elif event == "Insiderhandel":
            context = " Ett insiderköp kan vara intressant men ska inte ses som bevis på framtida kursuppgång."
        elif event == "Utdelning / återköp":
            context = " Kontrollera om utbetalningen finansieras av ett hållbart kassaflöde."
        elif event == "Ledning / styrelse":
            context = " Effekten beror på vilken roll som ändras och varför."
        elif event == "Produkt / lansering":
            context = " Det viktiga är om satsningen kan bli ekonomiskt betydelsefull, inte bara att den lanseras."
        return (
            "Möjlig caseförändring – verifiera",
            "Händelsen kan vara relevant för investeringscaset, men rubriken räcker inte för att avgöra hur stor effekten är." + context,
            2,
        )

    if event == "Analys / riktkurs":
        return (
            "Troligen sekundär information",
            "En riktkurs eller extern analys kan ge ett bra uppslag, men ändrar inte bolagets verksamhet i sig. Leta efter nya fakta bakom analysen innan du låter den påverka din syn på aktien.",
            1,
        )

    if event in {"Kursrörelse / marknadsreaktion", "Forumdiskussion"}:
        return (
            "Brus tills orsaken är verifierad",
            "En kursrörelse eller forumdiskussion visar att intresset har ökat, men säger inte varför bolagets verkliga värde skulle ha ändrats. Leta efter den bakomliggande bolagshändelsen först.",
            0,
        )

    return (
        "Oklart om caset förändrats",
        "Borsify kan inte avgöra från rubrikerna om investeringscaset faktiskt har förändrats. Behandla uppslaget som något att läsa vidare om, inte som ny bekräftad fundamental information.",
        1,
    )

def build_verified_ideas(mentions: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    if mentions.empty or scored.empty:
        return pd.DataFrame()
    keep = [c for c in [
        "Ticker", "Namn", "Pris", "Valuta", "Borsify Score", "INVEST Score", "SWING Score", "REVERSAL Score",
        "Värdering", "Kvalitet", "Risk", "Direktavkastning", "P/E", "ROE", "Skuld/eget kapital", "Riskflaggor", "Datatäckning"
    ] if c in scored.columns]
    merged = mentions.merge(scored[keep], on="Ticker", how="left", suffixes=("", "_score"))
    merged["Upptäcktsstyrka"] = merged.apply(discovery_strength, axis=1)

    def verdict(r: pd.Series) -> tuple[str, str]:
        b_num = pd.to_numeric(r.get("Borsify Score"), errors="coerce")
        q_num = pd.to_numeric(r.get("Kvalitet"), errors="coerce")
        risk_num = pd.to_numeric(r.get("Risk"), errors="coerce")
        cov_num = pd.to_numeric(r.get("Datatäckning"), errors="coerce")
        b = float(b_num) if pd.notna(b_num) else np.nan
        q = float(q_num) if pd.notna(q_num) else np.nan
        risk = float(risk_num) if pd.notna(risk_num) else np.nan
        cov = float(cov_num) if pd.notna(cov_num) else np.nan
        if not np.isfinite(b):
            return "Kan inte verifieras", "Aktien nämns externt men Borsify saknar tillräcklig marknadsdata för kontroll."
        if np.isfinite(cov) and cov < 0.45:
            return "För lite data", "Det finns för lite fundamental data för att ge idén grönt ljus."
        if b >= 70 and (not np.isfinite(q) or q >= 55) and (not np.isfinite(risk) or risk >= 50):
            return "Klarar första kontrollen", "Uppslaget har nu klarat Borsifys första kontroll av pris, kvalitet och risk. Läs ändå vad som faktiskt hänt i bolaget innan du agerar."
        if b >= 60:
            return "Värd att undersöka", "Idén är inte bortsorterad, men siffrorna är inte starka nog för en tydlig kvalitetsstämpel."
        return "Uppslag, inte fynd", "Aktien diskuteras eller syns i media, men Borsifys nyckeltal ger inte stöd för att lyfta den just nu."

    verdicts = merged.apply(verdict, axis=1, result_type="expand")
    merged["Borsify-granskning"] = verdicts[0]
    merged["Förklaring"] = verdicts[1]
    combos = merged.apply(combination_signal, axis=1, result_type="expand")
    merged["Kombinationssignal"] = combos[0]
    merged["Kombinationsförklaring"] = combos[1]
    merged["Idéprioritet"] = pd.to_numeric(combos[2], errors="coerce").fillna(0.0)
    impacts = merged.apply(case_impact_assessment, axis=1, result_type="expand")
    merged["Case Impact"] = impacts[0]
    merged["Case Impact Förklaring"] = impacts[1]
    merged["Case Impact Nivå"] = pd.to_numeric(impacts[2], errors="coerce").fillna(0).astype(int)
    combo_order = {
        "Ovanligt intressant kombination": 0,
        "Kvalitetsbolag i fokus": 1,
        "Möjlig återhämtningsidé": 2,
        "Kortsiktigt läge i fokus": 3,
        "Värt en närmare titt": 4,
        "Ingen särskild kombination": 5,
    }
    order = {"Klarar första kontrollen": 0, "Värd att undersöka": 1, "För lite data": 2, "Uppslag, inte fynd": 3, "Kan inte verifieras": 4}
    merged["_combo_order"] = merged["Kombinationssignal"].map(combo_order).fillna(9)
    merged["_order"] = merged["Borsify-granskning"].map(order).fillna(9)
    return merged.sort_values(["_combo_order", "_order", "Idéprioritet", "Borsify Score"], ascending=[True, True, False, False]).drop(columns=["_combo_order", "_order"]).reset_index(drop=True)
