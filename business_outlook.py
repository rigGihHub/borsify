"""Dated business context and conditional industry analysis, never fabricated alpha."""
from business_report_evidence import usable_business_evidence
from datetime import date
import math
import re
from urllib.parse import quote

import pandas as pd

REVIEWED = "2026-10-07"
# Company disclosures describe exposure, not independent proof of future growth.
PROFILES = {
 "MEDS.ST": ("MEDS driver ett svenskt nätapotek med receptbelagda läkemedel, receptfria läkemedel och apoteksprodukter.", "online_pharmacy", "https://corporate.meds.se/media/pressmeddelanden/2026/meds-delarsrapport-q2-2026-18-omsattningstillvaxt-och-38-tillvaxt-i-ebit/", "I rapporten för andra kvartalet 2026 beskriver MEDS uppstarten av ett logistikcentrum i Eskilstuna. Bedöm om kapaciteten ger lönsam försäljning och kassaflöde; en större anläggning bevisar inte framtida efterfrågan."),
 "HAFNI.OL": ("Hafnia transporterar oljeprodukter och kemikalier till sjöss med tankfartyg.", "tankers", "https://hafnia.com/about-hafnia/", "Produkt- och kemikalietankers ger exponering mot transportbehov, handelsvägar och fraktpriser."),
 "FRO.OL": ("Frontline transporterar råolja och raffinerade oljeprodukter med tankfartyg.", "tankers", "https://www.frontlineplc.cy/", "Transportvolymer och transportsträckor behöver vägas mot hur många nya fartyg som levereras."),
 "BWLPG.OL": ("BW LPG äger och driver fartyg som transporterar gasol, LPG, och bedriver även handel med produkten.", "lpg", "https://www.bwlpg.com/about/our-business/", "LPG är gasol, inte LNG. Efterfrågan från hushåll och petrokemi måste analyseras separat från råolja."),
 "SNM.OL": ("ShaMaran utvecklar och producerar olja och gas i Kurdistanregionen i Irak.", "oil", "https://shamaranpetroleum.com/company/corporate-profile/", "Geografisk koncentration innebär att exportmöjligheter och betalningar är centrala att kontrollera."),
 "NETC.CO": ("Netcompany utvecklar digitala system och plattformar för företag och offentlig sektor.", "digital", "https://netcompany.com/about-us/", "Bolaget beskriver AI-integrerade lösningar och europeisk digital infrastruktur som inriktningar. Intäkter och lönsamhet från dessa behöver verifieras."),
 "PACT.ST": ("Proact levererar IT-infrastruktur, datalagring, molntjänster, säkerhet och drift till organisationer.", "digital", "https://www.proact.eu/", "Hybridmoln och europeisk datakontroll är erbjudanden som kan möta kundbehov. Kontrollera återkommande tjänsteintäkter och marginaler."),
 "ALLEI.ST": ("Alleima tillverkar avancerade rostfria stål, speciallegeringar och lösningar för krävande industriella och medicinska användningar.", "materials", "https://www.alleima.com/en/about-us/", "Specialiserade material skiljer sig från vanligt bulkstål. Kontrollera försäljningsmixen mot medicinteknik, energi och övrig industri."),
 "INVE-B.ST": ("Investor äger och utvecklar noterade bolag, onoterade verksamheter genom Patricia Industries och investeringar i EQT.", "holding", "https://www.investorab.com/", "Utsikterna måste bedömas genom innehaven och deras vikt i substansvärdet; investmentbolag är ingen enhetlig bransch."),
 "INVE-A.ST": ("Investor äger och utvecklar noterade bolag, onoterade verksamheter genom Patricia Industries och investeringar i EQT.", "holding", "https://www.investorab.com/", "Analysera innehavens branscher, substansvärde och skuldsättning, inte bara moderbolagets redovisade vinst."),
 "HACK.ST": ("Hacksaw utvecklar kasinospel och en teknikplattform för speloperatörer och andra spelstudior.", "gaming", "https://www.hacksawgroup.com/en/about/", "OpenRGS låter externa spelstudior använda plattformen. Kontrollera om fler studior och spel faktiskt ökar uthålliga intäkter."),
 "FMM-B.ST": ("FM Mattsson Group utvecklar, tillverkar och säljer kranar och relaterade produkter för badrum och kök.", "building", "https://www.fmmattssongroup.com/en/press-release/interim-report-january-june-2026/", "Bolaget har utökat varumärkesportföljen med Bristan. Förvärvad tillväxt måste skiljas från organisk tillväxt och integrationskostnader."),
 "BAVA.CO": ("Bavarian Nordic utvecklar, tillverkar och säljer vacciner, bland annat för resenärer och statlig beredskap.", "health", "https://www.bavarian-nordic.com/media/382845/2026-q1-en.pdf", "Resevacciner och beredskapsbeställningar har olika efterfrågemönster. En stor statlig order behöver inte återkomma varje år."),
}
# Scenarios are explicitly analysis questions, not live market forecasts.
SCENARIOS = {
 "online_pharmacy": ("Apotek med digital distribution", "Återkommande läkemedelsbehov och effektiv distribution kan stödja försäljningen om kunderna stannar.", "Priskonkurrens, reglering och kostnader för lager och distribution kan pressa marginalen trots tillväxt.", "Aktiva kunder, återköp, receptandel, marginal och kassaflöde efter logistikinvesteringar. Jämför med konkurrerande nätapotek."),
 "digital": ("Tillväxtmöjlighet med teknikskifte", "Digitalisering, moln, dataskydd och AI kan skapa nya uppdrag och produkter.", "AI kan också automatisera debiterbart arbete; konkurrens och kundernas IT-budgetar kan pressa priserna.", "Organisk tillväxt, återkommande intäkter, kundbehållning och marginal efter AI-investeringar."),
 "tankers": ("Cyklisk bransch med omställningsrisk", "Längre handelsvägar och begränsat fartygsutbud kan stödja fraktpriser även utan stark volymtillväxt.", "Nya fartyg, kortare handelsvägar och lägre efterfrågan på fossila bränslen kan pressa lönsamheten.", "Fraktintäkt per dag, flottans orderbok, beläggning, skulder och kassaflöde över en hel fraktcykel."),
 "lpg": ("Cyklisk transportmarknad", "Gasolanvändning och längre handelsvägar kan öka behovet av LPG-transporter.", "Överutbud av fartyg, handelshinder och förändrad energimix kan minska intjäningen.", "LPG-handelsvolymer, transportsträckor, fartygsleveranser och fraktintäkter; skilj handel från rederidrift."),
 "oil": ("Cyklisk efterfrågan och långsiktig omställning", "Låga produktionskostnader och tillgänglig export kan ge kassaflöde även i en mogen marknad.", "Lägre oljepris, elektrifiering, exportstopp och fallande reserver kan urholka framtida intjäning.", "Produktionskostnad, reserver, investeringar, exportflöden, betalningar och känslighet för oljepriset."),
 "materials": ("Nischtillväxt inom cyklisk industri", "Material med höga prestandakrav kan få efterfrågan från energi, medicinteknik och effektivare industri.", "Svag industrikonjunktur, kundernas investeringsstopp och prispress kan väga tyngre än tekniktrender.", "Organisk orderingång per slutmarknad, produktmix, kapacitetsutnyttjande och marginal."),
 "holding": ("Blandade utsikter – bedöm innehaven", "Värdeskapande kan komma från innehavens tillväxt, förbättringar och disciplinerad kapitalallokering.", "Koncentration, dyrt värderade innehav, förvärv och skulder kan förstärka en nedgång.", "Genomlyst branschexponering, substansrabatt, skulder och innehavens kassaflöden."),
 "gaming": ("Skalbar affär med regulatorisk risk", "Nya spel, operatörer och plattformskunder kan öka intäkterna utan motsvarande kostnadsökning.", "Reglering, licensrisk, beskattning, spelansvar och beroende av framgångsrika spel kan begränsa tillväxten.", "Intäkter från reglerade marknader, kund- och spelkoncentration, licenser och nya spels varaktiga bidrag."),
 "building": ("Mogen marknad med konjunkturkänslighet", "Renovering och behov av vatten- och energieffektivitet kan skapa efterfrågan även utanför nyproduktion.", "Svagt bostadsbyggande, pressade hushåll och lågprisalternativ kan bromsa volymer och marginaler.", "Organisk försäljning, renovering kontra nybyggnation, orderläge och marginal exklusive förvärv."),
 "health": ("Långsiktiga behov men produktspecifik risk", "Medicinska behov, nya behandlingar och förebyggande vård kan ge efterfrågan.", "Studieresultat, godkännanden, patent, prispress och osäkra upphandlingar kan förändra utsikterna snabbt.", "Godkända produkter, studiefas, patent, finansiering och återkommande försäljning kontra engångsorder."),
 "bank": ("Mogen bransch under förändring", "Digital effektivisering och fler kunder kan stödja lönsamheten.", "Kreditförluster, räntemarginaler, reglering och nya konkurrenter kan pressa avkastningen.", "Kreditförluster, kapitaltäckning, räntenetto och kostnad per kund genom konjunkturen."),
 "property": ("Tillgångsbaserad och räntekänslig", "Efterfrågade lägen, uthyrning och effektivare byggnader kan förbättra kassaflödet.", "Refinansiering, vakanser och förändrade lokalbehov kan ge bestående värdefall.", "Uthyrningsgrad, hyrestillväxt, räntetäckning, låneförfall och typ av fastigheter."),
 "retail": ("Mogen marknad med förändrade köpvanor", "Starka varumärken, rätt distributionskanaler och återkommande kunder kan ta marknadsandelar.", "E-handel, lågpriskonkurrens och ändrade konsumtionsmönster kan göra delar av affären mindre relevanta.", "Jämförbar försäljning, bruttomarginal, lager, kundbehållning och kanalernas lönsamhet."),
 "industrial": ("Cyklisk industri med möjliga teknikdrivare", "Automation, service och effektivisering kan skapa affärer om bolagets produkter möter faktiska kundbehov.", "Svag orderingång, billigare alternativ och teknikskiften kan göra befintliga produkter mindre konkurrenskraftiga.", "Orderbok, organisk tillväxt, serviceandel, nya produkters försäljning och avkastning på investeringar."),
 "media": ("Strukturell förändring i distribution", "Digitala abonnemang och nischat innehåll kan skapa nya intäkter.", "Tryckt distribution och traditionell annonsering kan tappa till digitala alternativ; AI kan förändra innehållsmarknaden.", "Digitala intäkter, kundbortfall, betalningsvilja och om nya intäkter ersätter de gamla med lönsamhet."),
}
ALIASES = [("gaming", ("gambling",)), ("holding", ("investment company",)), ("oil", ("oil & gas e&p", "oil & gas integrated", "oil & gas drilling")), ("digital", ("software", "information technology services", "computer hardware")), ("building", ("building products", "residential construction", "building materials")), ("materials", ("steel", "specialty chemicals", "metal fabrication")), ("health", ("biotechnology", "drug manufacturers", "medical", "healthcare")), ("bank", ("banks", "insurance", "credit services")), ("property", ("real estate", "reit")), ("retail", ("retail", "apparel", "personal services")), ("media", ("publishing", "broadcasting", "advertising")), ("industrial", ("industrial", "machinery", "engineering & construction"))]

def clean(value):
    return value.strip() if isinstance(value, str) and value.strip().lower() not in {"nan", "none", "okänd", "unknown", "—"} else ""

def business_context(row, today=None):
    today = today or date.today()
    ticker = clean(row.get("Ticker")).upper()
    profile = PROFILES.get(ticker)
    industry = clean(row.get("Bransch"))
    sector = clean(row.get("Sektor"))
    summary = clean(row.get("Verksamhetsbeskrivning"))
    age = (today - date.fromisoformat(REVIEWED)).days
    fresh = 0 <= age <= 180
    if profile:
        description, category, source, initiative = profile
        provenance = f"Bolagets egen beskrivning · kontrollerad {REVIEWED}" + (" · behöver uppdateras" if not fresh else "")
    else:
        category = next((key for key, words in ALIASES if any(w in industry.lower() for w in words)), "")
        description = "Bolagsspecifik verksamhetsbeskrivning saknas i det sparade underlaget."
        if summary:
            # Keep the provider's language, explicitly labelled, without inventing a translation.
            sentences = re.split(r"(?<=[.!?])\s+", summary)
            description = " ".join(sentences[:2])[:650]
        source = "https://finance.yahoo.com/quote/" + quote(ticker, safe="") + "/profile/" if summary else ""
        provenance = "Yahoo Finance, originaltext · hämtad " + (clean(row.get("Fundamental hämtad")) or "okänd tidpunkt") if summary else "Ingen verifierad bolagsbeskrivning"
        initiative = "Ingen aktuell bolagsspecifik satsning har verifierats i detta underlag. Branschens möjligheter är inte bevis för bolagets tillväxt."
    report_evidence = usable_business_evidence(row, today)
    initiatives = [x["text"] for x in report_evidence if x["ämne"] == "Tillväxt och investeringar"]
    if initiatives:
        initiative = "Bolaget uppger i rapporten (originaltext): " + " ".join(initiatives)
    scenario = SCENARIOS.get(category)
    result = {"Verksamhet kort": description, "Verksamhet källa": source, "Verksamhet källstatus": provenance,
              "Bransch klassificering": category, "Bransch underlag": industry or sector or "Okänd bransch",
              "Bolagets framtidssatsning": initiative, "Bransch bedömd": bool(scenario),
              "Bransch källor": [], "Bransch analysdatum": today.isoformat(), "Bransch källfakta": "Ingen aktuell oberoende branschprognos är inläst. Möjligheter och hot nedan är ett analysramverk, inte bekräftad marknadsutveckling."}
    if scenario:
        label, opportunity, threat, checks = scenario
    else:
        label, opportunity, threat, checks = ("Otillräckligt branschunderlag", "Kan inte bedömas tillförlitligt utan tydligare verksamhets- och segmentdata.", "Avsaknad av branschdata är inte ett tecken på låg risk.", "Verifiera vad bolaget säljer, vilka kunderna är, konkurrenter och intäktsfördelning per segment.")
    if category == "digital":
        result["Bransch källor"] = [("OECD, 28 januari 2026 – företagens AI-användning 2025", "https://www.oecd.org/en/about/news/announcements/2026/01/ai-use-by-individuals-surges-across-the-oecd-as-adoption-by-firms-continues-to-expand.html")]
        result["Bransch källfakta"] = "OECD rapporterar ökad AI-användning bland företag under 2025. Det visar spridning av tekniken, inte hur mycket intäkter just detta bolag får från den."
    elif category in {"oil", "tankers"}:
        result["Bransch källor"] = [("IEA Oil 2025 – scenario till 2030, inte aktuell frakt- eller oljeprisprognos", "https://www.iea.org/reports/oil-2025/executive-summary")]
    if category in {"oil", "tankers"}:
        result["Bransch källfakta"] = "IEA:s Oil 2025 bedömde att global oljeefterfrågan skulle plana ut mot 2030. Det är ett daterat scenario, inte bevis för att efterfrågan redan minskar eller att branschen försvinner."
    if category in {"tankers", "lpg"}:
        result["Bransch källor"].append(("UNCTAD Review of Maritime Transport 2025 – fraktcykler och handelsvägar", "https://unctad.org/publication/review-maritime-transport-2025"))
        result["Bransch källfakta"] += " UNCTAD:s rapport 2025 beskriver hur geopolitik, handelsvägar och utbud påverkar fraktmarknadens volatilitet."
    observed = []
    for key, label2 in [("Omsättningstillväxt", "registrerad omsättningstillväxt"), ("Vinstmarginal", "registrerad vinstmarginal")]:
        try:
            v = float(row.get(key))
            if math.isfinite(v): observed.append(f"{label2} {v:.1%}")
        except (TypeError, ValueError): pass
    result.update({"Branschutsikt": label, "Bransch möjlighet": opportunity, "Bransch hot": threat, "Bransch att verifiera": checks,
                   "Bransch bolagskoppling": ("Tillgängliga bolagsmått: " + "; ".join(observed) + ". " if observed else "Bolagets tillväxt och lönsamhet kan inte verifieras här. ") + "En enskild period visar inte om branschtrenden ger uthållig tillväxt. Segmentdata och flerårsutveckling behövs.",
                   "Bransch slutsats": "Borsifys villkorade bedömning, inte en verifierad tillväxtprognos. På kort sikt styr även order och konjunktur; på lång sikt måste affärens relevans och lönsamhet bestå. Ingen extra betygspoäng ges enbart för ett branschtema."})
    result["Verksamhet rapportunderlag"] = report_evidence
    return result

def add_business_context(frame):
    if frame is None or frame.empty:
        return frame.copy() if isinstance(frame, pd.DataFrame) else pd.DataFrame()
    out = frame.copy()
    extra = pd.DataFrame([business_context(r) for _, r in out.iterrows()], index=out.index)
    return out.drop(columns=extra.columns, errors="ignore").join(extra)

def render_business_context(st, row, compact=False):
    context = business_context(row)
    st.markdown("**Vad gör bolaget?**")
    st.write(context["Verksamhet kort"])
    st.caption(context["Verksamhet källstatus"])
    st.markdown(f"**Branschutsikter: {context['Branschutsikt']}**")
    st.write("Möjlighet: " + context["Bransch möjlighet"])
    st.write("Risk: " + context["Bransch hot"])
    with st.expander("Verksamhet, framtid och källor", expanded=not compact):
        st.caption("Branschunderlag: " + context["Bransch underlag"] + " · ramverk kontrollerat " + REVIEWED)
        st.write("**Källbelagd bakgrund och begränsning:** " + context["Bransch källfakta"])
        st.write("**Bolagets exponering och satsningar:** " + context["Bolagets framtidssatsning"])
        st.write(context["Bransch bolagskoppling"])
        for item in context["Verksamhet rapportunderlag"]:
            st.markdown("**" + item["ämne"] + "**")
            st.write(item["text"])
            st.caption("Bolagets uppgift · " + str(item["period"]) + " · " + str(item["publicerad"]))
            st.markdown("[Rapportkälla](" + item["källa"] + ")")
        st.write("**Följ i nästa rapport:** " + context["Bransch att verifiera"])
        st.caption(context["Bransch slutsats"])
        if context["Verksamhet källa"]:
            st.markdown(f"[Verksamhetskälla]({context['Verksamhet källa']})")
        for label, url in context["Bransch källor"]:
            st.markdown(f"[{label}]({url})")
