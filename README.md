# Borsify v2.35.0

## v2.35.0 – Earnings Revisions & Inflection Engine

Den här versionen prioriterar fyndkvalitet framför fler funktioner. Den långsiktiga djupkontrollen analyserar nu även **förändring** i stället för bara nivåer:

- kvartalsvis omsättningstillväxt och acceleration,
- marginalförändring YoY/QoQ,
- FCF- och vinstförändring mot föregående år,
- EPS-estimatrevideringar när Yahoo/yfinance faktiskt har täckning,
- balans mellan analytikerhöjningar och -sänkningar,
- senaste rapporterade EPS-överraskning när den finns.

Resultatet visas som **Inflection Score** och **Inflection Signal**. Det är ett transparent förändringsindex, inte en prognos om framtida aktieavkastning. Positiv inflektion kan hjälpa ett redan fundamentalt godkänt case att prioriteras, men kan **aldrig rädda ett case som stoppats av Value Trap Risk**. Tydligt negativa EPS-revideringar eller bred försämring kan däremot sänka ett annars godkänt case till extra kontroll.

Borsify visar dessutom **VARFÖR NU?** för toppcasen. Om ingen tydlig inflektion kan verifieras säger appen det i stället för att skapa en berättelse. Saknade analytikerestimat lämnas saknade och ersätts inte med AI, riktkurser eller rubriker.

### Metodbegränsningar

Yahoo/yfinance har varierande estimattäckning mellan marknader och bolag. v2.28 är därför byggd så att kvartalsdata kan ge förändringsevidens även när analytikertabeller saknas. Modellen är ännu inte point-in-time-backtestad för fundamenta eller estimatrevideringar; Inflection Score ska därför betraktas som en prioriteringssignal som måste valideras vidare, inte som bevisad alpha.


## Nytt i v2.27.0 – Deep Case Engine: kvalitet före billig värdering

Den här releasen markerar ett tydligt skifte: utvecklingen prioriterar **kvaliteten på de få case som hamnar högst**, inte fler funktioner.

- Ny tvåstegsprocess för långsiktiga case. Den breda scanningen tar först fram finalister; endast de starkaste INVEST-kandidaterna hämtar därefter fleråriga resultat-, kassaflödes- och balansräkningsdata.
- Ny **Value Trap Risk 0–100** med transparenta röda flaggor för negativt/instabilt FCF, krympande omsättning, försämrad vinst, fallande marginal, stigande skuld och svag aktuell lönsamhet. Skalan är en regelbaserad riskindikator, inte en sannolikhet.
- Ny **Deep Confidence** som mäter hur mycket verifierbar flerårsdata analysen faktiskt bygger på. Tunn historik kan inte få hög confidence.
- Ny gate-first-rankning: ett bolag med hög INVEST Score men tydlig value-trap-risk får inte slå ett verifierat case bara genom ett högt grundbetyg. Borsify skapar medvetet **ingen ny ovärderad mega-score** i detta steg.
- Ny konkret **Devil's Advocate** och **Varför marknaden kan ha fel** baserad på observerade flerårstrender. Om ingen tydlig förbättring kan verifieras säger appen det.
- Analytikers riktkurs/potential har tagits bort ur själva **Värdering**-scoren. En riktkurs är en åsikt och ska inte kunna göra ett bolag matematiskt ”billigare”.
- FCF-yield har tagits bort ur **Growth**-delen av INVEST eftersom samma information tidigare indirekt räknades både som värdering och tillväxt.
- Djupdata cachas i 12 timmar och hämtas bara för en liten finalistpool för att hålla den breda scanningen rimligt snabb. Om Yahoo saknar statement-data degraderar caset till otillräcklig data i stället för att Borsify fyller i luckor.

### Kritisk nulägesanalys som ledde till ändringen

Genomgången av v2.26 visade flera strukturella svagheter i fyndmotorn: fundamentalrankingen byggde huvudsakligen på en aktuell Yahoo-snapshot; flerårig uthållighet kunde därför inte verifieras. Värdering kunde dessutom få hjälp av analytikers målpris, FCF-yield återanvändes i Growth, och den breda Borsify Score blandade fundamenta med ett setup-betyg som medvetet premierar rekyler/RSI-områden. Det innebär risk för falsk precision och för att billiga/fallande aktier ser mer attraktiva ut än deras verksamhetsutveckling motiverar.

Detta är **inte** löst fullt ut i v2.27. Kvarvarande högprioriterade brister är framför allt point-in-time estimatrevideringar, rapportöverraskningar, robusta katalysatordata, sektor-/bolagstypanpassning, historisk validering av fundamentalmodellen och survivorship-bias i universumen. INVEST-backtest ska därför fortfarande inte beskrivas som validerat.

### Verifieringsgräns

Enhetstester kan verifiera trendextraktion, riskregler, confidence och gate-rankning med syntetiska statement-data. Den här byggmiljön har inte internetåtkomst, så faktisk Yahoo-latens/täckning för liveuniversumet kan **inte** verifieras här och ska testas efter deployment.


## Nytt i v2.26.0 – Gör "Nytt sedan sist" handlingsbart

- Varje ny förändring har nu en direkt åtgärd: **Öppna Case Journal** för förändrade bevakade case eller **Öppna signalhistorik** för nya Radar-signaler.
- Eftersom Streamlit-flikar inte kan bytas programmässigt på ett robust sätt visas destinationen direkt på Överblick i en tydlig, stängningsbar panel. Borsify låtsas alltså inte att den har navigerat till en annan flik.
- Ny knapp **Markera som genomgången**. En explicit genomgången förändring försvinner ur "Nytt sedan sist" medan senare nya händelser för samma aktie fortfarande kan visas.
- Genomgångsstatus använder stabila händelsenycklar och påverkar aldrig signalhistoriken, Case Journal eller någon investeringsscore.
- Lokal SQLite fungerar direkt. För inloggade molnkonton finns en idempotent `reviewed_changes`-migration i `supabase_schema.sql`. Om den saknas degraderar appen säkert utan att övriga funktioner slutar fungera.


## Nytt i v2.25.0 – Nytt sedan sist

- Startsidan sparar tidpunkten för föregående besök och visar bara nya, tidsstämplade signaler och tydliga förändringar i bevakade case.
- Första besöket behandlas neutralt: äldre information märks inte felaktigt som ny.
- Streamlit-reruns under samma besök flyttar inte jämförelsepunkten; samma besök får därför en stabil förändringslista.
- Samma aktie kan bara ta en plats i listan och den viktigaste nya orsaken behålls.
- Funktionen är ett läst/oläst-lager och påverkar aldrig Borsify Score, INVEST, SWING eller REVERSAL.
- Lokal SQLite fungerar direkt. För inloggade molnkonton finns en idempotent `visit_state`-migration i `supabase_schema.sql`; appen degraderar säkert om den ännu inte körts.

## Nytt i v2.22.0 – Case Alert

- **Case Alert** kopplar ihop Case Journal, användarens egna Case-breaker-regler och mediabevakningen för bevakade aktier.
- En tydlig negativ händelse, exempelvis en vinstvarning, prioriteras extra högt när Borsifys egen mätbild samtidigt har försvagats eller en egen Case-breaker är utlöst.
- Rapport, förvärv och andra potentiellt casepåverkande händelser märks som viktiga att läsa men Borsify gissar inte positiv/negativ riktning från rubriken ensam.
- Case Alert kan även varna för intern försämring utan ny media och visa ny mediepuls utan att kalla det ett internt larm.
- Mediabevakningen för bevakade case hämtas på användarens begäran och återanvänder samma cache som Idéflödet; den körs inte i onödan vid varje Streamlit-rerun.
- Den senaste matchade originalrubriken och en länk till källan visas i bevakningscaset när sådan finns.
- Extern information påverkar fortfarande aldrig Borsify Score, INVEST, SWING eller REVERSAL. Case Alert är triage och uppföljning, inte köp-/säljråd.
- Ingen ny databas- eller Supabase-migration krävs för v2.22.0.

## Nytt i v2.21.0 – Case-breaker

Bevakade aktier kan nu få egna **case-breakers**: lägsta accepterade Borsify Score, kvalitet och riskpoäng samt största tillåtna scorefall från den första sparade analysen. 0 stänger av en regel. Borsify visar **Caset håller**, **Case-breaker nära** eller **Case-breaker utlöst** med vanlig svensk förklaring. En utlöst regel är en signal att granska investeringsidén på nytt – aldrig en automatisk säljorder.

Lokalt migreras SQLite automatiskt. För Supabase finns fyra `alter table ... add column if not exists` längst ned i `supabase_schema.sql`; de behöver köras i SQL Editor när v2.21.0 tas i drift med molnbevakning.


## Nytt i v2.13.0 – Kvalitet till rätt pris + Idéflöde

- Ny **Kvalitet till rätt pris**-kontroll för långsiktiga case. Den kombinerar aktuell kvalitet, värdering och risk och förklarar på vanlig svenska vad som talar för och vad som behöver granskas.
- Kontrollen är medvetet märkt som en **nulägesbild**. Borsify låtsas inte att dagens fundamenta bevisar 5–10 års uthållighet; point-in-time historiska fundamenta saknas fortfarande.
- Ny flik **Idéflöde**. Borsify kan hämta publika rubriker från ekonomimedia via Google News RSS och forumuppslag från Reddit r/Aktiemarknaden via publik Atom-feed.
- Externa omnämnanden används **endast för att hitta uppslag**. De ändrar inte Borsify Score, INVEST, SWING eller REVERSAL.
- Rubriker matchas mot bolagen i det analyserade universumet och varje match körs sedan genom Borsifys befintliga nyckeltal. Resultatet blir bland annat **Klarar första kontrollen**, **Värd att undersöka** eller **Uppslag, inte fynd**.
- Idéflödet visar separat **Upptäcktsstyrka** (hur tydligt/färskt bolaget dyker upp externt) och **Borsify-granskning** (vad siffrorna säger). På så sätt kan hype inte maskeras som fundamental kvalitet.
- Borsify återger rubrik och länk, inte hela artiklar. Källor kan tillfälligt sluta fungera eller ändra sina publika feeds; appen fortsätter då med övriga källor och visar en tydlig varning.
- Nya tester för feed-parsning, bolagsmatchning och kontrollen att hög extern uppmärksamhet **inte** kan ge ett svagt bolag grönt ljus.

## Nytt i v2.11.0 – målbaserad upptäckt, utdelningsläge och bättre bevakning

- Nytt val **Vad letar du efter?** med vanliga mål i stället för finansjargong: bästa möjligheter, långsiktigt, utdelning, billiga kvalitetsbolag, stora fall/återhämtning, kortsiktigt läge och stabilare aktier.
- Ny **Match Score** som rankar aktier efter det valda målet utan att ersätta den ordinarie Borsify Score.
- Ny sektion **Upptäck · bäst match för ditt mål** med fem lättlästa kandidater.
- Fördjupat **Utdelningsläge** med topp 5, direktavkastning, ungefärlig årlig utdelning på 10 000 kr och en försiktig bedömning av utdelningens hållbarhet utifrån utdelningsandel, kvalitet och risk.
- Bevakningslistan visar nu **Borsifys skäl just nu**, aktuell hämtad kurs, användarens egen anledning att bevaka och **Mitt intressepris** i stället för den mer tvetydiga etiketten målkurs.
- Nybörjarordlistan har utökats med volatilitet, likviditet, stop-loss, diversifiering och hävstång.
- Metodfliken har fått en enkel riskgenomgång. Borsify fokuserar fortsatt på vanliga aktier och använder inte hävstång som ett sätt att förstora modellens signaler.
- Ingen förändring av kärnformlerna för Borsify Score, INVEST, SWING eller REVERSAL i denna release.



## Nytt i v2.10.0 – enklare språk, utdelningsfilter och OMXS30-benchmark

- Ny kryssruta **Bara aktier med direktavkastning** i sidopanelen. När den är aktiv visas bara aktier med registrerad positiv direktavkastning. Det går även att ange en miniminivå i procent.
- Aktieanalyserna är omskrivna till enklare svenska. P/E, ROE, RSI, SMA200, direktavkastning, drawdown, profit factor och ATR förklaras så att användaren inte behöver kunna finansjargong i förväg.
- Ny utfällbar **Förklara börsorden enkelt** i detaljanalys och Edge Lab.
- Edge Labs portföljtest jämför nu Borsifys historiska kapitalutveckling med **OMXS30 under samma tidsperiod**, normaliserat till 100 vid start.
- Benchmarkdelen visar total avkastning, ungefärlig årstakt (CAGR), max fall från topp och en förenklad riskjusterad kvot, tillsammans med en vanlig-svenska-tolkning.
- Benchmarktexten varnar för att OMXS30-serien här inte är ett totalavkastningsindex med utdelningar, så jämförelsen är diagnostisk och inte perfekt.
- Ingen ändring av själva Borsify-, INVEST-, SWING- eller REVERSAL-scoremodellerna i denna release.

## Nytt i v2.6.0 – handelsfriktion och positionsstorlek

Edge Lab har fått ett ekonomiskt stresstest ovanpå walk-forward-resultatet. Det använder endast de out-of-sample-trades som redan valts av walk-forward-testet och låter användaren lägga på courtage tur/retur, spread + slippage tur/retur samt vald andel kapital per trade.

Resultatet visar netto-träffsäkerhet, netto-median per trade, netto-profit factor, sekventiell kapitalutveckling och max drawdown. Om den historiska edgen försvinner efter rimliga handelsfriktioner flaggar appen detta tydligt i stället för att lyfta bruttoresultatet.

Simuleringen är avsiktligt konservativ och enkel. Den modellerar inte skatt, samtidig portföljexponering, likviditet, orderdjup, partiella fills eller verklig exekvering. Den ska användas för att sålla bort ekonomiskt svaga signaler, inte för att lova live-resultat.


## v2.5.0 – Edge Lab

- Ny flik **Edge Lab** för historiskt test av tekniska SWING- och REVERSAL-proxys på valfri ticker.
- Visar antal signaler, träffsäkerhet, median-/snittavkastning, profit factor och jämförelse mot alla giltiga handelsdagar som baslinje.
- Testet använder endast bakåtblickande pris- och volymdata för att undvika look-ahead bias.
- INVEST backtestas medvetet inte ännu eftersom Borsify saknar point-in-time historiska fundamenta; att använda dagens fundamenta historiskt skulle ge missvisande resultat.
- Varning vid små stickprov och tydlig markering när signalen inte visar edge mot baslinjen.
- Ny modul `edge_lab.py` och grundtester i `tests/test_edge_lab.py`.

Edge Lab är ett signaltest, inte ett komplett portföljbacktest. Courtage, spread, slippage, skatt, survivorship bias och historiska indexmedlemskap ingår ännu inte.

## v2.1.2 – Streamlit duplicate-key hotfix

- Rättar `StreamlitDuplicateElementKey` som kunde uppstå när samma aktie renderades både på Överblick och Dagens fynd i samma Streamlit-körning.
- Bevakningsknappar får nu kontextunika nycklar per vy (`overview`/`daily`).
- Ingen ändring av INVEST-, SWING-, REVERSAL- eller Borsify Score-modellerna.

## v2.1.1 – aktuell kurs i lyfta case
- Visar aktuell hämtad kurs, valuta och dagsförändring direkt på INVEST-, SWING- och REVERSAL-kandidater.
- Visar aktuell kurs även för bästa kandidat på Överblick och i Dagens fynd-korten.
- Nästa kandidater och jämförelsetabellen innehåller kurs, kursdag och dagsförändring.
- Scoringmodellerna är oförändrade från v2.1.0.



## v2.1.0 – live polish

- Korrigerad kontrast i Streamlit-metrics/KPI-kort när appen körs med mörkt tema.
- Metric-värden och etiketter får nu explicita läsbara färger i stället för att ärva vit text från temat.
- Statusrader använder temats textfärg i stället för hårdkodad mörk text.
- Mobilvyn har kompaktare och mer läsbara KPI-kort.
- Yahoo-fel visas nu som en tydlig datakällevarning och förklarar att övriga aktier fortfarande analyserats.
- Ingen ändring av Borsify Score/scoringmodellen.

Borsify är en svensk aktiescreener som rankar aktier med **Borsify Score 0–100** utifrån värdering, kvalitet, marknadsläge, utdelning och risk. Modellen är ett prioriteringsverktyg för vidare analys, inte ett köp- eller säljråd.

## Nytt i v2.0.0 – Dagens fynd på riktigt

Den här releasen fokuserar på kärnfrågan: **vilka få aktier är mest värda att undersöka idag, varför just idag och vad talar emot dem?**

- **Dagens kortlista**: Borsify lyfter automatiskt fram högst fem kandidater i stället för att bara visa en lång ranking.
- **Dagens relevans 0–100**: en separat triage ovanpå vanliga Borsify Score. Den väger främst in total score, aktuellt marknadsläge och förändring sedan föregående snapshot.
- **Riskgrind**: grova riskflaggor som negativ lönsamhet, hög skuldsättning eller tydligt fallande lång trend kan begränsa dagens prioritet även om grundscoren är hög.
- **Varför idag**: för varje kandidat visas konkreta orsaker, t.ex. förbättrad score, stark setup, RSI i rekylzon, avstånd från 52-veckorstopp eller momentum.
- **Vad har förändrats**: de största förändringarna i Värdering, Kvalitet, Marknadsläge, Utdelning eller Risk visas mot föregående registrerade snapshot.
- **Kontrollera innan du går vidare**: Borsify visar de viktigaste modellriskerna och flaggar även låg datatäckning eller att historik saknas.
- **Snabb jämförelsetabell** för kortlistan samt den tidigare rena topplistan enligt Borsify Score kvar under den.

### Hur Dagens relevans fungerar

Dagens relevans är medvetet **inte samma sak som Borsify Score**. Grundscoren försöker bedöma aktiens samlade screeningprofil. Dagens relevans försöker prioritera *timing för vidare analys* bland redan starka kandidater.

Ungefärlig viktning:

- 55 % Borsify Score
- 20 % Marknadsläge
- 10 % Kvalitet
- 5 % Värdering
- 10 % förändring i Borsify Score

Låg datatäckning ger avdrag. Grova riskflaggor kan både ge avdrag och sätta tak på relevansen. Detta är en heuristik för prioritering, inte en prognos för framtida avkastning.

## Prestanda och data

v1.9 behåller förbättringarna från v1.8:

- bulk-hämtning av kurshistorik för valt universum,
- kurscache 15 minuter,
- fundamentalcache 6 timmar,
- separat fallback för ticker som saknas i bulkdata,
- datastämplar för senaste kursdag och fundamental hämtning,
- striktare filter för saknade börsvärden/omsättningsdata.

## Start lokalt

```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Supabase

v1.9 kräver **ingen ny databasmigrering jämfört med v1.7/v1.8**. Om du uppgraderar från en äldre version behöver den medföljande `supabase_schema.sql` fortfarande vara körd.

Streamlit använder:

```toml
APP_ACCESS_PASSWORD = "CHOOSE_A_STRONG_PASSWORD"
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
```

## Automatisk scanning och e-post

`.github/workflows/daily-scan.yml` kör den schemalagda vardagsscanningen. Repository Secrets:

- `BORSIFY_SUPABASE_URL`
- `BORSIFY_SUPABASE_SERVICE_ROLE_KEY`
- `BORSIFY_RESEND_API_KEY` – om e-post ska skickas
- `BORSIFY_EMAIL_FROM` – verifierad avsändare hos Resend

Service-role-nyckeln och Resend-nyckeln ska aldrig läggas i appkoden eller committas.

## Datakälla och begränsningar

Marknads- och fundamentaldata hämtas via Yahoo Finance/yfinance och kan vara fördröjd, ofullständig eller inkonsekvent mellan bolag. `universe.csv` innehåller ett kuraterat svenskt universum och är inte garanterat en officiell komplett Nasdaq Stockholm-lista.

Borsify Score är relativ och påverkas av vilka aktier som finns i det analyserade universumet. Dagens relevans bygger dessutom delvis på tidigare snapshots; innan historik finns används ett neutralt förändringsvärde. Kontrollera alltid bolagets rapporter, IR-information, kassaflöde, skuldsättning och aktuell nyhetsbild innan investeringsbeslut.


## Public-ready v2.1.0

Den här releasen är förberedd för ett publikt GitHub-repo och Streamlit Community Cloud. Produktnamnet är **Borsify**, domänreferenser använder **borsify.se**, och genererade Python-cachefiler är borttagna.

Lägg aldrig riktiga nycklar i repot. Streamlit-värden ska läggas i appens **Secrets** och GitHub Actions-värden ska läggas i repository **Actions secrets**. `.streamlit/secrets.toml` och lokala SQLite-filer ignoreras av Git.

För Streamlit används exempelvis:

```toml
APP_ACCESS_PASSWORD = "CHOOSE_A_STRONG_PASSWORD"
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_ANON_KEY = "YOUR_SUPABASE_ANON_KEY"
```

För den schemalagda GitHub Action-körningen används vid behov:

- `BORSIFY_SUPABASE_URL`
- `BORSIFY_SUPABASE_SERVICE_ROLE_KEY`
- `BORSIFY_RESEND_API_KEY`
- `BORSIFY_EMAIL_FROM`

`BORSIFY_SUPABASE_SERVICE_ROLE_KEY` får aldrig läggas i Streamlit-klientens Secrets eller i källkoden.

### Åtkomst till den publikt hostade appen

När `APP_ACCESS_PASSWORD` finns i Streamlit Secrets stoppas appen innan någon marknadsdata eller användarvy laddas. Besökaren måste först ange lösenordet. Om nyckeln saknas är appen öppen, vilket är praktiskt vid lokal utveckling men inte rekommenderat för den publika testmiljön.

Detta skyddar **appen**, inte källkoden: ett publikt GitHub-repo kan fortfarande läsas av andra. Därför får inga hemligheter finnas i repot.
## v2.1.0 hotfix

- Rättar Streamlit Cloud-krasch i `ProgressColumn` genom att använda nyckelordsargument för `min_value` och `max_value`.
- KPI-kort använder nu Streamlits egna temavariabler i stället för fasta ljusa färger, så texten är läsbar i både mörkt och ljust tema.
- Felande tickers visas fortsatt individuellt i datakällans expander.
- Scoringmodellen är oförändrad.


## v2.1.0 – Three Engines
- INVEST Score för långsiktig screening av värdering, kvalitet, risk, tillväxt och kassaflöde.
- SWING Score för dagar–veckor med setup, trend mot SMA200, volymkvot och risk.
- REVERSAL Score för möjliga överreaktioner med dagsfall, drawdown, RSI, kvalitet och riskgrind.
- Textanalys på aktiesidan som förklarar varför aktien kan vara intressant, vilka datapunkter som stöder caset och vilka modellrisker som måste kontrolleras.
- Dagens fynd visar tre separata topplistor så lång och kort sikt inte blandas ihop.

Modellerna är screeningverktyg, inte prognoser eller köp-/säljråd. v2.1 använder befintlig Yahoo/yfinance-data; historisk värdering, estimatrevideringar och backtesting återstår innan modellen kan sägas ha verifierad edge.
## Nytt i v2.5.0 – Edge Lab Universumtest

- Kör samma SWING- eller REVERSAL-proxy över många svenska aktier samtidigt.
- Visar antal testade aktier, antal signaler, träffsäkerhet mot baslinje, median-edge, profit factor och andel aktier med positiv edge.
- Visar resultat per ticker för att upptäcka om en strategi bara råkar fungera på några få bolag.
- Kräver bredare stickprov innan appen beskriver en signal som lovande.
- Fortsatt inget historiskt INVEST-backtest utan point-in-time fundamenta; det skulle skapa look-ahead bias.


## v2.5.0 · Marknadsregimer i Edge Lab

Edge Lab kan nu dela upp historiska SWING- och REVERSAL-resultat efter OMXS30-regim: **Risk-on**, **Neutral** och **Risk-off**. Regimen byggs enbart av information som fanns vid respektive datum (index mot SMA200, SMA50 mot SMA200 och 60-dagars momentum), vilket undviker framtidsinformation i klassificeringen.

Både enskild ticker och universumtest visar träffsäkerhet, medianutfall, edge mot baslinje och profit factor per regim. Universumtestet varnar dessutom när en signal verkar tydligt regimberoende. Det är ett diagnostiskt lager för att senare kunna anpassa signaltrösklar efter marknadsklimat; produktionsmodellen ändras inte automatiskt i denna version.

## Nytt i v2.5.0 – walk-forward / out-of-sample

Edge Lab kan nu göra ett första **walk-forward-test** för SWING och REVERSAL. I varje fold optimeras scoretröskeln endast på en äldre träningsperiod och fryses sedan under nästa, osedda testperiod. Träningsobservationer vars framtida utfall korsar testgränsen tas bort för att minska läckage.

Walk-forward-resultatet visar bland annat out-of-sample-träffsäkerhet, medianavkastning, edge mot baslinje, profit factor, andelen positiva testfönster och hur stabil den valda scoretröskeln är. Upprepade signaler som ligger i samma framtida utfallsfönster de-klustras så att flera dagar i samma setup inte räknas som oberoende trades.

Detta är fortfarande ett **signaltest**, inte ett fullständigt handelsbacktest. Courtage, spread, slippage, skatt, position sizing och portföljkapital modelleras inte. INVEST-motorn backtestas inte med dagens fundamenta eftersom det skulle skapa look-ahead bias.

## v2.7.0 – Portföljnivå i Edge Lab

Edge Lab kan nu simulera ett gemensamt kapital över många aktier med max antal samtidiga positioner, målallokering per position, courtage och spread/slippage. Kandidater samma dag prioriteras efter högst score, samma aktie kan inte öppnas dubbelt samtidigt och kapital binds tills den valda signalhorisonten löper ut. Resultatet visar bland annat equity curve, exponering över tid, max drawdown, profit factor och signaler som avvisades på grund av kapacitetsbrist.

I v2.7 bokfördes öppna positioner till insatt kapital mellan entry och exit. **Detta har ersatts i v2.9.0 av daglig mark-to-market med historiska stängningskurser.** Skatt, utdelningar, orderdjup, partial fills och verklig live-exekvering ingår fortfarande inte.



## v2.9.0 – Daglig mark-to-market i portföljtestet

- Öppna positioner värderas nu varje handelsdag med historisk stängningskurs i stället för att ligga kvar på anskaffningsvärdet fram till exit.
- Equity curve, exponering och max drawdown fångar därmed orealiserade rörelser under innehavstiden.
- Positionsstorlek vid nya signaler utgår från aktuell mark-to-market-equity, inte enbart bokfört kapital.
- Equity-datan innehåller även investerat marknadsvärde, investerat anskaffningsvärde, realiserad P/L och orealiserad P/L.
- ATR-stop och riskbudget fungerar tillsammans med den dagliga MTM-värderingen.
- Full vald tur/retur-friktion bokförs vid exit. Framtida exitkostnad periodiseras inte i öppna positioners dagliga MTM, vilket anges tydligt i gränssnittet.
- Fortfarande diagnostiskt backtest: gap-through, orderdjup, skatt och verkliga fills modelleras inte.

## v2.8.0 – Riskstyrning i Edge Lab

- Riskstyrd positionsstorlek utifrån vald risk per trade.
- ATR(14)-baserat stop-avstånd med trailing-only data och försiktiga min/max-gränser.
- Tak för sammanlagd öppen stop-risk i portföljen.
- Historiska stops kontrolleras mot efterföljande dagslägsta fram till normal horisontexit.
- Portföljvyn visar max öppen stop-risk, stop-andel och signaler som nekats av risktaket.
- Trade-loggen visar stop-avstånd och om positionen stoppades.
- Stop-simuleringen antar fill på stopnivån och modellerar inte gap-through; resultatet ska därför ses som diagnostik, inte exekveringsgaranti.

## v2.14.0 – Utländska marknader

- Ny marknadsväljare i sidopanelen: Sverige, USA, Norden exkl. Sverige, Tyskland och Storbritannien.
- Kuraterade startuniversum med stora/likvida aktier för varje utländsk marknad.
- Marknadsspecifika jämförelseindex där ett tydligt index används: OMXS30, S&P 500, DAX och FTSE 100.
- Norden exkl. Sverige blandar DKK/NOK/EUR och visar därför ingen förenklad benchmark i Edge Lab ännu i stället för en missvisande jämförelse.
- v2.14 använde lokala valutor i filtertexterna. Den begränsningen är löst från v2.15 genom SEK-omräkning före filtrering.
- Edge Labs universumtest använder nu det valda marknadsuniversumet i stället för att alltid använda Sverige bred.
- Marknadsregim och portföljbenchmark i Edge Lab följer valt marknadsindex där benchmark finns.
- Idéflödet har kompletterats med internationell ekonomimedia och Reddit r/stocks. Extern uppmärksamhet påverkar fortfarande inte Borsify Score utan används bara för uppslag som sedan granskas av Borsifys nyckeltalsmodell.

Listorna är kuraterade startuniversum och ska inte tolkas som fullständiga eller officiella indexmedlemslistor. Yahoo Finance kan ändra symboler, datatillgänglighet och fundamental täckning över tid.

## v2.16.0 – Valutaomräkning till SEK

- Utländska aktiekurser visas både i handelsvalutan och ungefärligt omräknade till SEK.
- Börsvärde och genomsnittlig dagsomsättning räknas om till SEK före filtrering, så storleks- och likviditetsfilter blir jämförbara mellan marknader.
- Valutakurser hämtas via Yahoo Finance och cachas i 15 minuter tillsammans med prisdata.
- Stöd för USD, EUR, GBP, DKK, NOK samt förberett stöd för CHF, CAD och JPY.
- Londonnoteringar som anges i pence (GBp/GBX) konverteras först till GBP och därefter till SEK.
- Originalkurs och originalvaluta bevaras alltid. SEK-värdet markeras som ungefärligt eftersom aktiekurs och valutakurs inte nödvändigtvis har exakt samma tidsstämpel.


## v2.16.0 hotfix
- Fixar NameError på Överblick när Datastatus renderas efter v2.15.0.
- Marknad och benchmark skickas nu explicit till startsidan.
- Saknad tidigare snapshot behandlas inte längre som något användaren bör kontrollera eller som en risksignal för aktien.


## v2.16.0 – Global Radar & Mediepuls
- Nytt marknadsval **Alla marknader** med ett begränsat globalt radaruniversum för snabb jämförelse mellan regioner.
- Global referens använder VT som praktisk proxy; detta förklaras tydligt som referens, inte exakt benchmark.
- Idéflödet visar **Mediepuls**: om ett bolag fått tydligt fler omnämnanden senaste 24 timmarna. Pulsen påverkar aldrig Borsify Score.
- Kvalitet till rätt pris har fått en extra sammanfattning på vanlig svenska för nybörjare.
- Ingen kärnscore har ändrats i denna release.


## v2.18.0 – Händelseradar · varför pratas det om aktien?

- Idéflödet klassificerar nu rubriker i konkreta händelsetyper: rapport/resultat, prognos/guidance, analys/riktkurs, insiderhandel, order/kontrakt, förvärv/bud, utdelning/återköp, emission/finansiering, ledningsförändring, regulatoriskt/juridiskt, produkt/lansering, kursrörelse samt vinstvarning/tydlig försämring.
- Varje matchat bolag får `Huvudhändelse`, eventuella fler `Händelsetyper` och en kort förklaring på vanlig svenska om vad användaren bör kontrollera.
- Rubrikerna bakom ett uppslag märks med händelsetyp så användaren snabbare kan förstå varför bolaget syns.
- Händelseklassningen är deterministisk rubriksortering, inte sentimentanalys. Den ändrar aldrig Borsify Score, INVEST, SWING eller REVERSAL och ska alltid verifieras mot originalkällan.
- Forumrubriker utan tydlig bolagshändelse märks som `Forumdiskussion` i stället för att Borsify gissar en orsak.

## v2.17.0 – Kombinationsradar

- Idéflödet kan nu upptäcka när extern uppmärksamhet sammanfaller med stark Borsify-data.
- Nya etiketter: **Ovanligt intressant kombination**, **Kvalitetsbolag i fokus**, **Möjlig återhämtningsidé** och **Kortsiktigt läge i fokus**.
- En separat **Läs först**-prioritet används bara för att sortera externa uppslag. Den består av 72 % Borsify Score och 28 % upptäcktsstyrka och är uttryckligen inte en investeringsscore eller avkastningsprognos.
- För den starkaste kombinationsflaggan krävs bland annat flera oberoende mediekällor; forumaktivitet ensam räcker inte.
- Media/forum ändrar fortfarande aldrig Borsify Score, INVEST, SWING eller REVERSAL.

## v2.19.0 – Case Impact · ändrar nyheten själva investeringscaset?
- Idéflödet skiljer nu mellan händelser som kan ändra bolagets vinst/risk och sådant som främst är brus eller andrahandsåsikter.
- Ny etikett **Ändrar detta investeringscaset?** med tydlig, nybörjarvänlig förklaring.
- Vinstvarning markeras som ny risk att kontrollera direkt.
- Rapport, prognos, förvärv och regulatoriska händelser markeras som potentiellt caseförändrande utan att Borsify gissar om riktningen.
- Emission/finansiering får särskild riskförklaring, inklusive extra varning när den befintliga riskbilden redan är svag.
- Riktkurser/analytikeråsikter behandlas som sekundär information tills nya fundamentala fakta identifieras.
- Kursrörelser och forumdiskussioner behandlas som brus tills bakomliggande orsak verifierats.
- Case Impact påverkar inte Borsify Score, INVEST, SWING eller REVERSAL.

## v2.21.0 – Case Journal · följ om caset faktiskt förändras

- Bevakade aktier får en **Case Journal** direkt i bevakningslistan.
- Journalen använder redan sparade dagssnapshots och kräver därför ingen ny databas eller Supabase-migration.
- Borsify jämför dagens score och delpoäng med den första sparade analysen och beskriver på vanlig svenska om den egna mätbilden har stärkts, försvagats eller varit ungefär oförändrad.
- Tydliga förändringar i Kvalitet, Värdering, Marknadsläge, Utdelning och Risk lyfts separat.
- En enkel tidslinje visar de senaste sparade analyserna och förändringen från start.
- Användarens egen bevakningsanteckning och intressepris ligger kvar bredvid journalen, så den ursprungliga tanken kan jämföras med hur datan utvecklats.
- Journalen säger uttryckligen att förändringen gäller **Borsifys mätbild**, inte ett automatiskt köp- eller säljbeslut.
- Ingen kärnscore eller signalmodell ändras i denna release.
## v2.25.0 – Dagens fokus
- Ny startsammanfattning som prioriterar högst tre saker att läsa först.
- Samlar dagens kandidater, verkliga förändringar i bevakade case och nya Radar-signaler i samma vy.
- Dubbletter per ticker tas bort så ett bolag inte kan fylla hela listan.
- Fokus-rankingen används bara för läsordning och påverkar aldrig Borsify Score, INVEST, SWING eller REVERSAL.
- Språket är avsiktligt vardagligt: varje punkt säger vad som hänt, varför det är relevant och vad användaren bör kontrollera härnäst.

## Nytt i v2.25.0 – Tidsmedvetet Dagens fokus
- Startsidan anpassar arbetsrubriken efter tid på dagen: **Inför börsöppning**, **Under dagen**, **Efter börsdagen** eller **Helgens fokus**.
- Nya Radar-signaler får en försiktig färskhetsmarkering som **Nytt i dag**, **Sedan i går** eller **Senaste dagarna**.
- Färskhet kan påverka vad som visas först, men påverkar aldrig Borsify Score, INVEST, SWING eller REVERSAL.
- Åtgärdstexten anpassas efter läget: förberedelse före öppning, kontroll under dagen eller uppföljning efter stängning.
- Tidsläget är en UX-hjälp och inte en officiell börskalender; helgdagar och halvdagar kan avvika.


## v2.35.0 – Mispricing Engine

Den långsiktiga djupkontrollen har nu ett separat förväntningslager. Borsify försöker inte påstå att den känner marknadens verkliga prognos. I stället räknar den ut transparenta **expectation hurdles**: vilken årlig EPS-tillväxt som ungefär krävs för 10 % årlig avkastning över fem år om slutvärderingen är P/E 15, 20 respektive 25. En separat förenklad FCF-lins jämför aktuell FCF-yield med samma avkastningshurdle.

Hurdlarna jämförs endast med verifierbar tillväxtdata. Positiv felprissättning får inte rädda ett case med hög Value Trap Risk, medan en tydligt krävande värdering kan sänka ett tidigare godkänt djupcase till **Kräver extra kontroll**. Mispricing-bedömningen är en triage av prisets krav – inte en DCF, kursprognos eller sannolikhet.

Viktigt: exitmultiplarna 15/20/25 och 10 %-hurdlen är synliga antaganden. De ska senare kalibreras/valideras per sektor och marknad när point-in-time data finns; de får inte optimeras bakåt enbart för bästa backtestresultat.


## v2.35.0 – Bull / Base / Bear & Asymmetry Engine

Den nya `scenario_engine.py` bygger transparenta femårsscenarier för långsiktiga djupcase.
Bear, Base och Bull använder synliga antaganden för EPS-tillväxt och framtida P/E.
Tillväxten ankras i verifierad flerårsdata, forward EPS där den finns och en försiktigt
begränsad inflektionsjustering. Multipeln mean-revertas i stället för att dagens höga
värdering automatiskt extrapoleras.

Motorn beräknar modellerad upp-/nedsida, annualiserad avkastning och en enkel
asymmetrikvot (Base-uppsida relativt Bear-nedsida). Value Trap Risk gör bear-scenariot
hårdare och kan även sänka Base-antagandet. Extrem tillväxt och extrema multiplar
begränsas uttryckligen för att minska falsk precision.

Detta är scenarioanalys – inte kursmål eller prognoser. Saknas positiv EPS, pris eller
tillräcklig tillväxthistorik returnerar motorn `Otillräcklig data`.


## v2.35.0 – Confidence & Case Quality Gate

Den långsiktiga topplistan använder nu en gate-first-modell som kräver stöd från flera oberoende analysdelar i stället för en ny viktad totalscore. Fyra stöd kontrolleras: flerårig fundamental kvalitet, färsk inflektion/estimatrevidering, möjlig felprissättning och Bear/Base/Bull-asymmetri. Datatäckning fungerar som förutsättning och tydlig value-trap-risk, negativ inflektion, krävande värdering eller svag scenario-risk/reward kan stoppa ett case.

Scenario Engine från v2.30 är nu integrerad i den faktiska djupanalysen och UI:t. Bear/Base/Bull-antaganden och scenarioasymmetri visas för varje case när data räcker. `Case Confidence` betyder evidenstäckning, inte sannolikheten för positiv avkastning. INVEST används först efter gate-modellen som en tie-breaker, så hög gammal score kan inte ensam skapa ett toppcase.


## v2.35.0 – Catalyst Engine & WHY NOW

Long-term finalister får nu en separat katalysatoranalys som försöker svara på vad som
konkret kan få marknaden att omvärdera bolaget och ungefär när. Motorn skiljer mellan
schemalagda kontrollpunkter (t.ex. nästa rapport), data-baserad fundamental inflektion,
skuld-/kassaflödesförbättring och rubrikbaserade bolagshändelser.

Rubriker får aldrig ensamma bevisa ekonomisk effekt. Order, guidance, återköp m.m. märks
som potentiella katalysatorer men originalkällan måste verifieras. Vinstvarning/sänkt
guidance blir i stället en riskflagga som kan stoppa promotion av caset.

Case Quality Gate har nu fem oberoende pelare: fundamental kvalitet, färsk inflektion,
felprissättning, scenarioasymmetri och katalysator. Ett Toppcase kräver stöd från alla fem
samt tillräcklig evidenstäckning. En kommande rapport är inte positiv bara för att den finns.


## v2.35.0 – Short-Term Alpha Engine 2.0

Kortsiktig fyndmotor för ungefär 1–6 månader. Den gamla SWING/REVERSAL-logiken finns kvar
för historik och Edge Lab, men huvudlistan för kortsiktiga case använder nu en hårdare modell.

Motorn prioriterar:
- relativ styrka mot vald marknadsbenchmark över 1/3/6 månader,
- trend mot SMA50/SMA200,
- kontrollerat momentum,
- handelsaktivitet/volym,
- färska vinst- och estimatsignaler,
- konkreta katalysatorer.

Ett stort kursfall, stor drawdown eller låg RSI ger aldrig pluspoäng i sig. Kombinationen
svag lång trend + negativt momentum, tydligt försämrade vinstsignaler eller ny extern risk
kan stoppa ett case helt. Ett kortsiktigt Toppcase kräver dessutom minst en positiv
fundamental/revisions- eller katalysatorsignal; en snygg kursgraf räcker inte ensam.

Short Alpha Score är ett screeningindex, inte en prognos eller sannolikhet. Confidence mäter
datatäckning/evidens. Benchmarkdata hämtas nu för upp till ett år så relativ styrka kan
beräknas på 1, 3 och 6 månader.


## v2.35.0 – Edge Lab för Short Alpha 2.0

Edge Lab kan nu rekonstruera den tekniska delen av Short Alpha 2.0 point-in-time över
historiska dagsdata. Testet använder endast information som fanns på respektive datum:
relativ styrka mot vald benchmark, SMA50/SMA200-trend, 1/3/6-månadersmomentum och
handelsaktivitet. Anti-falling-knife-reglerna appliceras historiskt på samma sätt.

Framtida 1-, 3- och 6-månadersutfall läggs på först efter att signalserien byggts. Edge Lab
visar tröskelanalys, träffsäkerhet, medianutfall, andel stora vinster/förluster och ett
walk-forward-test där tröskeln väljs på äldre träningsdata innan nästa tidsperiod utvärderas.

Delsignaler kan också delas i kvartiler för att undersöka om exempelvis starkare relativ
styrka faktiskt följts av bättre 3-månadersutfall i den valda aktiens historik.

Viktig begränsning: historiska estimatrevideringar och katalysatorer backfylls inte.
Borsify har ännu inte point-in-time-historik för dessa faktorer. v2.34 validerar därför
en teknisk Short Alpha-proxy, inte hela live-modellen. Detta är medvetet för att undvika
look-ahead bias.


## v2.35.0 – Recommendation Ledger & Outcome Learning

Borsify fryser nu de faktiska kort- och långsiktiga finalisterna per dag, profil, marknad
och modellversion innan framtida kursutfall är kända. Snapshoten innehåller bland annat
rank, ingångspris, gate, score, confidence, evidensantal, WHY NOW, katalysator och de
centrala delsignalerna. Även finalister som inte blev Toppcase sparas. Det är avsiktligt
för att minska rekommendations-/survivorship bias i framtida kalibrering.

Utfall mäts på exakta framtida handelssessioner från den frysta rekommendationsdagen:
1/3/6 månader för kortsiktiga case och 6 månader/1 år/2 år för långsiktiga case. Om appen
inte kördes exakt vid horisonten används den historiska stängningskursen på rätt
handelssession – inte dagens pris som ersättning.

Edge Lab har fått en Recommendation Ledger-vy med senaste frysta beslut, antal mogna
utfall, medianutfall, andel positiva utfall och kalibrering per gate. Borsify ändrar ännu
inte några modellvikter automatiskt från ledgern; små samples ska inte överoptimeras.

SQLite fungerar direkt. För Supabase krävs de nya tabellerna `recommendation_ledger` och
`recommendation_outcomes` i `supabase_schema.sql`. Om migrationen saknas fortsätter appen
utan ledger i molnet och visar migration-needed-status internt i stället för att krascha.


## v2.36.1 – Hotfix för djupanalys

Byter scalar cell-assignments i deep/short finalist pipelines från `DataFrame.loc` till `DataFrame.at`. Detta gör att list-/dictvärden som Catalyst Candidates och stöd/veto-listor lagras som ett objekt i en cell i stället för att Pandas försöker tolka värdet som en kolumniterabel. Fixar kraschen `Must have equal len keys and value when setting with an iterable`.


## v2.36.1 – Pandas iterable assignment hotfix

Hotfix for Streamlit/Pandas runtime crash in deep and short finalist builders.
`.at` alone was insufficient when a new column did not yet exist because Pandas
internally fell back to `.loc`. All dynamically-added assessment columns are now
created first as object dtype, then populated cell-by-cell. This safely supports
lists and dictionaries such as Case Supports, Catalyst Candidates and similar
structured evidence fields.

## v2.36.1 – Runtime hotfix for structured assessment fields

Replaced all cell-by-cell writes of deep/short assessment dictionaries with a separate
object-typed DataFrame followed by index join. This completely avoids Pandas scalar
assignment for list/dict fields and fixes the Streamlit Cloud crash path shown at
build_deep_longlist line 891.


## v2.36.1 – Fråga Borsify AI på varje rekommendation

Varje kort- och långsiktig rekommendation har nu en egen fråga/svar-yta:
`Fråga Borsify AI om rekommendationen`.

Användaren kan ställa fria frågor, exempelvis:
- Varför rekommenderar du Alleima när den redan ligger så högt?
- Vad är det starkaste argumentet emot caset?
- Vad skulle få Borsify att ändra uppfattning?
- Är det här ett värderingscase eller ett momentumcase?
- Vilket antagande i Base-scenariot är mest känsligt?

AI:n får en begränsad, strukturerad kontext med just den rekommendationens faktiska
Borsify-data. För kortsiktiga case omfattar den bland annat Short Alpha, relativ styrka,
trend, momentum, revisionsbild, katalysatorer, varningar och motargument. För långsiktiga
case omfattar den bland annat Case Gate, evidens, value-trap-risk, inflektion, mispricing,
Bear/Base/Bull-scenarier, katalysatorer och Devil's Advocate.

Systeminstruktionen förbjuder AI:n att hitta på bolagsfakta som saknas i caset. Den måste
skilja på absolut aktiekurs, tidigare kursuppgång, relativ styrka och faktisk värdering,
lyfta starkaste motargumentet och förklara vad som skulle kunna ändra Borsifys bedömning.

Aktivering i Streamlit Secrets:
`OPENAI_API_KEY = "..."`
Valfritt:
`OPENAI_MODEL = "gpt-5.6-luna"`

Om nyckeln saknas kraschar inte appen. Då visas ett tydligt regelbaserat reservsvar och
gränssnittet förklarar att extern AI inte är aktiverad. API-nyckeln skickas aldrig till
webbläsaren eller lagras i GitHub.


## v2.36.1 – Aktuell kurs på alla rekommendationer

Alla rekommendationskort visar nu senaste tillgängliga kurs tydligt direkt i headern,
tillsammans med dagsförändring där den finns. Detta gäller både Short Alpha 1–6 månader,
långsiktiga djupcase och Dagens fynd. Senaste kursdag visas när Prisdatum finns.

Syftet är att användaren direkt ska kunna bedöma om ett case fortfarande är relevant
och undvika att behöva öppna detaljanalysen bara för att se priset.
