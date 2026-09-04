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


## v2.51.0 – Hotfix för djupanalys

Byter scalar cell-assignments i deep/short finalist pipelines från `DataFrame.loc` till `DataFrame.at`. Detta gör att list-/dictvärden som Catalyst Candidates och stöd/veto-listor lagras som ett objekt i en cell i stället för att Pandas försöker tolka värdet som en kolumniterabel. Fixar kraschen `Must have equal len keys and value when setting with an iterable`.


## v2.51.0 – Pandas iterable assignment hotfix

Hotfix for Streamlit/Pandas runtime crash in deep and short finalist builders.
`.at` alone was insufficient when a new column did not yet exist because Pandas
internally fell back to `.loc`. All dynamically-added assessment columns are now
created first as object dtype, then populated cell-by-cell. This safely supports
lists and dictionaries such as Case Supports, Catalyst Candidates and similar
structured evidence fields.

## v2.51.0 – Runtime hotfix for structured assessment fields

Replaced all cell-by-cell writes of deep/short assessment dictionaries with a separate
object-typed DataFrame followed by index join. This completely avoids Pandas scalar
assignment for list/dict fields and fixes the Streamlit Cloud crash path shown at
build_deep_longlist line 891.


## v2.51.0 – Fråga Borsify AI på varje rekommendation

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


## v2.51.0 – Aktuell kurs på alla rekommendationer

Alla rekommendationskort visar nu senaste tillgängliga kurs tydligt direkt i headern,
tillsammans med dagsförändring där den finns. Detta gäller både Short Alpha 1–6 månader,
långsiktiga djupcase och Dagens fynd. Senaste kursdag visas när Prisdatum finns.

Syftet är att användaren direkt ska kunna bedöma om ett case fortfarande är relevant
och undvika att behöva öppna detaljanalysen bara för att se priset.


## v2.51.0 – AI-kostnadsmätare

Borsify visar nu uppskattad kostnad för varje lyckad AI-fråga och ackumulerad kostnad
för innevarande kalendermånad. Beräkningen använder faktisk tokenanvändning som returneras
av Responses API. Standardpriset för `gpt-5.6-luna` är centraliserat i `ai_cost.py`.

Mätaren visar USD och, när USD/SEK kan hämtas via Borsifys befintliga Yahoo-FX-cache,
även ungefärlig kostnad i SEK.

Inloggade Supabase-användares usage sparas i den nya tabellen `ai_usage`.
Kör v2.51.0-delen i `supabase_schema.sql` för molnpersistens. Om tabellen saknas eller
användaren inte är inloggad faller appen säkert tillbaka till lokal SQLite.

Kostnadsmätaren är en uppskattning, inte OpenAI-fakturan. Den lagrar endast lyckade
Borsify-AI-anrop och prisar dem enligt den taxa som finns i appversionen.


## v2.51.0 – Prisrelevans i AI + renare rekommendationskort

- Aktuell kurs visas nu på en egen fullbreddsrad på kort- och långsiktiga rekommendationer
  för att undvika Streamlits avkortning av exempelvis `134,00 SEK`.
- Svenska decimaler används i kursvisningen och kursdag/dagsförändring visas på samma rad.
- Short Alpha-casets AI-kontext innehåller nu även tillgängliga värderings- och kvalitetsdata:
  P/E, Forward P/E, P/B, EV/EBITDA, FCF-yield, ROE, vinstmarginal, skuld/eget kapital,
  risk, värderingsscore, kvalitetsscore, 52v-position, RSI och aktuell kursdata.
- AI-instruktionen kräver nu att frågor av typen "är caset fortfarande relevant från dagens kurs?"
  väger ihop värdering, kvalitet/risk och korttidssignaler. Hög aktiekurs i kronor får aldrig
  automatiskt tolkas som dyr värdering.
- AI:n får fortfarande inte kvantifiera uppsida om scenario-/värderingsunderlaget inte räcker.
- Kostnadsmätaren är nedtonad till `AI denna månad: ≈ X kr · N frågor`.
  USD, tokens och modell ligger bakom detaljexpanders.


## v2.51.0 – Rekommendationens relevans nu

Varje kort- och långsiktigt finalistcase jämförs nu med den senaste frysta
rekommendationen från en tidigare dag för samma ticker, horisont, profil och marknad.

Borsify visar en separat status:
- `Ny rekommendation`
- `Fortfarande relevant`
- `Caset har stärkts`
- `Mindre attraktivt än vid signal`
- `Caset har försvagats`

Bedömningen är deterministisk och är inte en ny avkastningsprognos. Den väger bland
annat förändrad modellscore, förändrad gate, hårda motbevis samt kursförändringen sedan
den tidigare frysta rekommendationen. En kursuppgång gör inte automatiskt aktien "dyr".
Om kursen har stigit tydligt utan motsvarande förstärkning i modellstödet markeras i
stället att värderingen bör kontrolleras på nytt.

Från v2.51.0 fryser Recommendation Ledger dessutom relevanta värderingsfält
(P/E, Forward P/E, P/B, EV/EBITDA, FCF-yield m.fl.) så framtida jämförelser kan beskriva
om värderingsbilden faktiskt har förändrats, inte bara kursen.

Samma dags frysta poster används aldrig som jämförelse för samma dags rerun, vilket
förhindrar meningslös självjämförelse.


## v2.51.0 – Case Plan: vad måste hända härifrån?

Varje kort- och långsiktigt finalistcase får nu en explicit uppföljningsplan:
- Tes
- Vad som bekräftar caset
- Varningssignal
- Case-breaker
- Nästa kontrollpunkt
- Prisrelevans

Planen är deterministisk och byggs endast av redan verifierad Borsify-data. Den hittar
inte på riktkurser, rapportdatum, katalysatorer eller sannolikheter.

För kortsiktiga case används bland annat relativ styrka, trend, revisionssignal,
katalysatorer, vetoer och Relevans nu. För långsiktiga case används bland annat
inflektion, mispricing, katalysatorer, Case Quality Gate, Devil's Advocate och
Bull/Base/Bear-scenarier där de faktiskt kan beräknas.

Prisregeln sätter ingen godtycklig procentuell stop/rekommendationsgräns. Om scenariodata
saknas säger Borsify uttryckligen att underlaget inte räcker. Om ett gammalt scenario
finns kräver planen att det räknas om vid väsentligt ändrad kurs i stället för att
återanvända gamla uppsidesiffror.

Case-planen skickas också med till Borsify AI så användaren kan fråga varför en viss
bekräftelse, varningssignal eller case-breaker är viktig.


## v2.51.0 – Global startsida med fyra Top 3-listor + Mina aktieköp

Överblick börjar nu med fyra separata topp 3-rankningar:
1. 1–2 dagar / Daytrader
2. 1 vecka–3 månader
3. 1–5 år
4. Resten av livet

Alla marknader är nu standardval. Det globala universumet använder hela Borsifys
nuvarande kuraterade täckning i Sverige, USA, Danmark, Norge, Finland, Tyskland och
Storbritannien. UI:t säger uttryckligen att detta ännu inte betyder samtliga börser i
samtliga länder.

Varje horisont har en separat transparent rankinglogik. Daytrading prioriterar momentum,
volym/aktivitet, RSI, trend och risk. Mellanhorisonten kombinerar 1–3 månaders momentum
med kvalitet/risk/värdering. 1–5 år prioriterar INVEST/kvalitet/värdering/risk. "Resten
av livet" viktar kvalitet, robusthet, ROE och marginal högst och kallas uttryckligen en
kandidatlista, inte ett löfte om evigt ägande.

Ny sektion "Mina aktieköp · säljkoll" låter användaren registrera ticker, köpkurs, antal,
köpdatum och anteckning. Tabellen visar aktuell kurs, utveckling, värde, färgkodad
modellstatus och Borsifys skäl. Statusarna är BEHÅLL, BEVAKA, VINSTSÄKRA? och OMPRÖVA.
Detta är en modellbaserad beslutsindikator och inte personlig finansiell rådgivning.

Innehav sparas lokalt i SQLite eller privat per inloggad användare i Supabase efter att
v2.51.0-migreringen i supabase_schema.sql har körts.


## v2.51.0 – Landfilter i Topplistor + bredare Avanza-inspirerad marknadstäckning

De fyra Top 3-listorna på Överblick har nu ett gemensamt multiselect-filter för land.
Användaren kan välja ett eller flera länder och samtliga fyra horisonter räknas om inom
det valda urvalet.

"Alla marknader" har samtidigt breddats till de 15 länder/marknader som motsvarar
Avanzas nuvarande digitala direktutbud enligt Avanzas publika information:
Sverige, USA, Kanada, Danmark, Norge, Finland, Tyskland, Storbritannien, Frankrike,
Nederländerna, Belgien, Portugal, Italien, Spanien och Schweiz.

Borsifys universum är fortfarande ett kuraterat, likviditetsorienterat urval av aktier
på dessa marknader – inte ännu varje enskilt värdepapper som Avanza tillåter handel i.
Detta är medvetet: vi vill inte kalla täckningen komplett innan vi faktiskt kan
identifiera, hämta och kvalitetssäkra hela den handlingsbara listan.

Nya regionala listor har lagts till för Kanada, Frankrike, Nederländerna, Belgien,
Italien, Spanien, Schweiz och Portugal. Befintliga listor för Sverige, USA, Norden,
Tyskland och Storbritannien finns kvar.


## v2.51.0 – Avanza Universe v1

Borsifys marknadsuniversum har flyttats till en separat skalbar katalog
`avanza_universe.csv` med ticker, land och nivå. Första breda versionen innehåller
586 unika aktier i 15 länder.

För utländska marknader kan användaren välja:
- Snabbt kärnurval
- Brett universum (beta)

Topplistorna behåller landfiltret. Överblick visar dessutom en täckningstabell per land
med antal kärnaktier, breda tillägg och total katalogstorlek.

Detta ska inte tolkas som att Borsify redan täcker exakt alla aktier som går att handla
hos Avanza. Avanza Universe är en växande, Avanza-inspirerad katalog. En ticker i den
breda nivån kan dessutom sluta fungera eller byta symbol hos datakällan; scanmotorn
tolererar sådana fel och exkluderar aktier vars marknadsdata inte kan verifieras.

Arkitekturen gör att katalogen kan växa mot tusentals värdepapper utan att alla tickers
behöver hårdkodas i app.py.


## v2.51.0 – Universe Quality Control

Det breda marknadsuniversumet får nu en separat datakvalitetskontroll innan en aktie
tillåts delta i ranking. Kontrollen bedömer bland annat:
- giltig aktuell kurs
- verifierbart kursdatum
- tillräcklig kurshistorik
- bolagsnamn och valuta
- täckning av centrala fundamentala datapunkter

Status:
- VERIFIERAD
- DELVIS VERIFIERAD
- EXKLUDERA

En aktie hårdexkluderas endast när marknadsdatan inte räcker för en pålitlig ranking,
exempelvis ogiltig kurs, saknat kursdatum eller mycket kort historik. Saknade
fundamentala data får inte fyllas i eller gissas; aktien kan i stället märkas
DELVIS VERIFIERAD.

Överblick visar Universe Quality Control för den aktuella körningen, inklusive
verifierade/delvis verifierade/hårt exkluderade tickers samt analyserbar täckning per
land. Topplistorna visar också datakvalitetsstatus på varje kandidat.

QC är strikt separerad från investeringsbedömningen: VERIFIERAD betyder att datan går
att använda, inte att aktien är ett bra köp.


## v2.51.0 – Persistent Universe QC & Quarantine

Universe Quality Control är nu beständig över tid i stället för att börja om från noll
vid varje scanning.

Borsify sparar per ticker:
- senaste QC-status
- antal lyckade och misslyckade kontroller
- fel i följd
- senast kontrollerad
- senast verifierad
- senaste problemorsak
- eventuell karantän till datum/tid

Tre separata hårda QC-misslyckanden krävs innan en ticker sätts i sju dagars karantän.
Samma fel får inte räknas flera gånger bara för att Streamlit gör omkörningar under
samma dag. En senare lyckad verifiering nollställer felserien och häver karantän.

Före varje scan hoppas aktivt karantänsatta tickers normalt över. Användaren kan välja
"Omtesta karantän denna körning" för att tvinga fram ett nytt test.

Borsify har också en datakälle-säkring. Om en mycket stor del av hela scanbatchen
plötsligt misslyckas behandlas saknade hämtningar som ett möjligt Yahoo/dataleverantörs-
problem och ger inte automatiskt individuella QC-strikes. Detta minskar risken för
masskarantän vid ett externt driftfel.

Överblick visar Persistent QC med historik, aktiv karantän, felserier, senast verifierad
och scanens träffgrad. SQLite fungerar lokalt. För beständig molnlagring per användare
ska v2.45-migreringen i `supabase_schema.sql` köras.


## v2.51.0 – Buy Quality Gate

De fyra horisontlistorna är nu strikt köp-orienterade. Borsify rankar inte längre bara
de tre högsta relativa kandidaterna och kallar dem Top 3. Varje kandidat måste först
klara ett separat minimifilter för sin tidshorisont.

Grundprincip:
- 1–2 dagar: kräver tillräckligt horisontscore och undviker bland annat extrem RSI,
  mycket svag handelsaktivitet och tydligt negativ kort trend.
- 1 vecka–3 månader: kräver tillräckligt score samt rimlig trend, kvalitet och risk.
- 1–5 år: kräver tillräckligt score, INVEST-nivå, kvalitet och risk samt stoppar
  allvarliga breda riskflaggor.
- Resten av livet: har högst krav på uthållig kvalitet, riskprofil, lönsamhet och ROE.

Om färre än tre aktier klarar filtret visas färre än tre. Om ingen klarar det visas
"Inget köpcase klarar Borsifys minimikrav..." i stället för att fylla ut listan.

Varje godkänd kandidat märks tydligt "KÖPCASE · klarar Buy Quality Gate" tillsammans
med de viktigaste stöden i filtret.

Gränserna är modellregler och inte bevisad framtida avkastning. Särskilt 1–2-dagars-
modellen behöver fortfarande valideras point-in-time i Edge Lab innan den kan beskrivas
som en verifierad trading-edge.


## v2.51.0 – Daytrader Validation Lab

Edge Lab har fått en separat valideringsmotor för förstasidans köpmodell
"1–2 dagar · Daytrader".

Valideringen är point-in-time på pris/volymnivå:
- signalen byggs av information som fanns efter stängning dag t
- antaget köp sker först nästa handelsdags öppning
- utfall mäts efter 1 respektive 2 handelsdagar
- roundtrip-kostnad för courtage + spread/slippage kan anges i basis points
- brutto och netto hålls isär
- median, träffsäkerhet, median-edge mot baslinjen, profit factor, värsta trade och
  5-percentil kan beräknas
- sekventiella walk-forward/OOS-fönster använder en FRYST köpgräns och optimerar inte
  tröskeln i efterhand

Valideringsstatus kan vara:
- Ej validerad
- Svagt/blandat historiskt stöd
- Ingen tydlig historisk edge
- Historiskt lovande – ej bevisad edge

Motorn får aldrig kalla historiken "bevisad alpha".

Viktig begränsning: dagens live-Daytrade Score innehåller 10 procent Risk, och Risk
innehåller delvis fundamentala datapunkter. Borsify har ännu inte point-in-time-historik
för dessa fundamenta. Backtestet använder därför en kausal teknisk RiskProxy och är en
nära proxy, inte en exakt historisk replay av live-modellen.

Ytterligare begränsningar som visas i UI:
- survivorship bias eftersom dagens tickeruniversum används bakåt i tiden
- historiska Avanza-handelsrestriktioner saknas
- ingen intradagsorderbok
- ingen modell för verklig orderfyllnad
- Yahoo-historik kan innehålla databrister

Detta steg ändrar INTE produktionsvikterna automatiskt. Syftet är att falsifiera eller
stödja modellen innan en framtida kalibrering görs.


## v2.51.0 – Bred Daytrader-validering + enklare svenska

Daytrader Validation Lab kan nu testa samma frysta 1–2-dagarsregel på flera aktier
samtidigt. Användaren väljer antal aktier, historiklängd, 1 eller 2 handelsdagars
innehavstid och en total kostnad för köp + försäljning.

Resultatet visas både samlat, per land och per aktie. Syftet är att se om signalen
verkar fungera brett i stället för att dra slutsatser från enstaka aktier. Ett positivt
historiskt resultat beskrivs alltid försiktigt och får inte framställas som garanti för
framtida vinst.

v2.48 gör också en första bred språkgenomgång av användargränssnittet. Exempel:
- "ETF/proxy/totalavkastningsindex" i världsmarknadsförklaringen har ersatts med en
  konkret förklaring av att fonden VT äger aktier från många länder och används som en
  ungefärlig jämförelse.
- momentum förklaras som hur kursen utvecklats den senaste tiden
- fundamentaldata skrivs som bolagsuppgifter där det går
- profit factor visas som vinst/förlust-kvot
- drawdown visas som största fall från en tidigare topp
- OOS/walk-forward förklaras som nya testperioder med oförändrade regler
- spread/slippage förklaras som att verkligt köp/säljpris kan bli lite sämre än det
  pris man ser på skärmen

Grundregel för Borsifys UI: en person som aldrig köpt en aktie ska kunna förstå
huvudbudskapet utan att öppna en ordlista. Tekniska termer kan finnas i fördjupning
när de behövs, men ska då förklaras direkt på vanlig svenska.


## v2.51.0 – Enkel svenska i hela Borsify

Den här versionen gör en systematisk språkgenomgång av appens huvuddelar:
Överblick, Upptäck, Bevakning, Analysera och Metod.

Målet är att huvudbudskapet ska gå att förstå även för en person som aldrig har köpt
en aktie och inte känner till ekonomiska facktermer.

Exempel på ändringar:
- Buy Quality Gate visas som Borsifys minimikrav för köp.
- Edge Lab visas som Historiska tester.
- walk-forward/OOS förklaras som senare testperioder där reglerna inte ändras för att
  göra resultatet snyggare.
- benchmark förklaras som jämförelse med marknaden.
- Case-breaker visas som "Vad skulle få dig att tänka om kring aktien?".
- Bear/Base/Bull visas som Svagt scenario, Grundscenario och Starkt scenario.
- Value Trap visas som risk för värdefälla.
- Mispricing beskrivs som frågan om aktiens pris kan vara fel.
- Confidence beskrivs som hur bra underlaget är.
- katalysator beskrivs i huvudflödet som en händelse som kan ändra marknadens syn.
- EPS förklaras som vinst per aktie och FCF som fritt kassaflöde i fördjupade texter.
- CAGR visas som genomsnittlig förändring per år.
- tekniska portfölj- och backtesttexter har skrivits om med konkreta exempel på vad
  testet faktiskt gör.

En ny hjälpfunktion `plain_finance_text()` förenklar även text som skapas av analys-
motorerna innan den visas. Beräkningarna och de interna datanycklarna ändras inte.

Tekniska termer får fortfarande finnas i metodfördjupning när de behövs för
transparens, men de ska inte vara ett krav för att förstå Borsifys slutsats.


## v2.50.0 – Säkrare datakontroll + skarpare köpkrav

### Datakällan får inte sätta aktier i karantän av misstag
Den tidigare skyddsregeln kunde bedöma en stor hämtning som tillräckligt frisk om bara
tre aktier lyckades, även om hundratals andra misslyckades. Exempel: 3 av 586 kunde
felaktigt räcka.

Ny regel:
- 0 försök: neutralt, inget fel.
- högst 10 aktier: minst 50 procent måste fungera.
- fler än 10 aktier: minst 20 procent måste fungera.
- om datakällan inte klarar detta behandlas saknade aktier som ett tillfälligt
  datakälleproblem och får ingen felmarkering som kan leda till karantän.

Detta gör persistent QC fail-safe vid breda Yahoo-problem.

### Hårdare krav för att kallas KÖPCASE
Köpgränserna höjs:
- 1–2 dagar: 66 -> 68
- 1 vecka–3 månader: 64 -> 66
- 1–5 år: 63 -> 65
- mycket lång sikt: 66 -> 68

Borsify kräver dessutom tillräckligt med relevant data för respektive tidshorisont.
En hög score som till stor del bygger på neutrala standardvärden för saknade data får
inte längre lika lätt bli ett köpcase.

Krav på underlag:
- 1–2 dagar: minst 4 av 5 centrala kurs/handelsmått.
- 1 vecka–3 månader: minst 4 av 5 relevanta trend/kvalitetsmått.
- 1–5 år: minst 3 av 4 kärnmått och minst 55 procent total datatäckning.
- mycket lång sikt: minst 4 av 5 kvalitetsmått och minst 60 procent datatäckning.

Dessutom:
- 1–3 månader måste ha minst en tydlig positiv bekräftelse via positiv tremånaders-
  utveckling eller god bolagskvalitet.
- 1–5 år måste ha en tillräckligt stark långsiktig kärna.
- mycket lång sikt kräver minst två tydliga tecken på uthållig kvalitet.

Topplistorna heter nu "Bästa köp" och fylls fortfarande aldrig ut med svagare kandidater.
Noll godkända kandidater betyder noll köp.

Viktigt: de skarpare gränserna är kvalitetsregler, inte bevisad historisk alpha.
De ska utvärderas mot rekommendationsutfall innan ytterligare kalibrering.


## v2.51.0 – Köpkorten svarar på fyra frågor

Topplistornas kort har gjorts om för att hjälpa en oerfaren användare fatta vad
Borsify faktiskt menar utan att först tolka poäng, RSI eller andra börsord.

Varje KÖPCASE svarar nu direkt på:
1. Varför köpa?
2. Varför just nu?
3. Största risken.
4. Vad skulle få Borsify att ändra sig?

Svar byggs regelbaserat från den data Borsify redan har. Funktionen hittar inte på
nyheter, framtida händelser eller bolagsfakta.

De mer tekniska siffrorna finns kvar, men ligger bakom "Visa siffrorna bakom
bedömningen". Där finns Borsifys betyg för tidshorisonten, datakvalitet och relevanta
kurs-/kvalitetsmått.

Detta ändrar inte rankingformeln eller köpgränserna från v2.50.0. Syftet är att göra
beslutsunderlaget begripligare och låta användaren börja med slutsatsen och sedan
öppna siffrorna vid behov.


## v2.52.0 – Nära köpsignal + undvik att jaga aktier

Borsify kan nu visa aktier som ännu inte klarar köpkraven men ligger nära. Dessa visas
separat som "Nära köpsignal" och får aldrig blandas ihop med riktiga KÖPCASE.

För att få visas som nära köp måste aktien:
- ligga högst fem poäng under den riktiga köpgränsen,
- sakna allvarliga data- och riskproblem,
- inte redan vara kraftigt översträckt,
- fortfarande vara underkänd av det vanliga köpfiltret.

Borsify visar sedan "Vad saknas?" med högst två konkreta saker som behöver förbättras,
till exempel högre handelsaktivitet, förbättrad kort trend eller starkare långsiktig
helhetsbedömning.

### För sent att köpa?
En ny regelbaserad kontroll letar efter tecken på att aktien redan rört sig ovanligt
långt, till exempel:
- extremt hög kortsiktig kursstyrka,
- mer än 7 procent upp på en dag,
- mer än 25 procent upp på en månad,
- mer än 55 procent upp på tre månader,
- kurs långt över sin långsiktiga trend.

För 1–2 dagar och 1 vecka–3 månader kan en tydligt översträckt aktie stoppas från
köplistan trots ett högt betyg. För längre tidshorisonter visas i stället en tydlig
varning så att stark långsiktig kvalitet inte försvinner enbart på grund av en snabb
kursuppgång.

Detta är en riskkontroll, inte en prognos om att kursen måste falla. Trösklarna är
avsiktligt försiktiga och ska senare utvärderas mot sparade rekommendationsutfall
innan de kalibreras.


## v2.53.0 – Risk jämfört med möjlig uppsida

För de två kortaste tidshorisonterna bygger Borsify nu en regelbaserad handelsplan
från faktisk kurshistorik. AI används inte för att skapa några prisnivåer.

Planen innehåller när tillräcklig data finns:
- ett ungefärligt köpområde med dagens kurs som utgångspunkt,
- en nivå där den kortsiktiga analysen kan betraktas som fel,
- första och eventuellt andra tidigare kurstopp ovanför dagens pris,
- avståndet till fel-nivån,
- möjlig uppsida dividerad med möjlig nedsida.

Fel-nivån utgår från en nylig botten och aktiens normala dagsrörelse. Modellen begränsar
också hur långt bort nivån får hamna så att en gammal extrem botten inte skapar ett
meningslöst upplägg.

Målnivåerna måste vara priser som aktien faktiskt tidigare har handlats vid. Om ingen
tidigare tydlig kurstopp finns ovanför dagens kurs visar Borsify "Ingen tydlig målnivå"
i stället för att konstruera en artificiell riktkurs.

Status:
- Attraktivt: minst 2,0 gånger möjlig uppsida per riskenhet till första nivån.
- Godkänt: minst 1,4 gånger.
- Svagt: minst 1,0 gånger.
- Dåligt: under 1,0 gånger.

Risk/uppsida används som sekundär sortering mellan redan godkända kort- och
medelfristiga köpcase. Den får inte ensam göra en underkänd aktie till KÖPCASE.

Viktigt: nivåerna är tekniska referenspunkter från historisk kursdata, inte prognoser,
riktkurser eller garantier. Trösklarna är ännu inte bevisade och bör senare utvärderas
mot Borsifys sparade rekommendationsutfall.


## v2.54.0 – Relativ styrka + sektorstyrka

För korta och medelfristiga köpcase jämför Borsify nu aktiens kursutveckling med:
- andra aktier på samma marknad i den aktuella körningen,
- andra aktier i samma sektor och på samma marknad,
- hur sektorn som helhet går jämfört med marknaden.

Exempel: en aktie som har stigit 5 procent är inte automatiskt stark om jämförbara
aktier på samma marknad har stigit mer. Borsify försöker därför skilja verklig
relativ styrka från en allmän börsuppgång.

Jämförelsen använder medianen för de aktier som faktiskt finns i den aktuella
Borsify-körningen. Sektorjämförelse kräver minst tre aktier med data i samma sektor
och marknad. Om underlaget är för litet lämnas jämförelsen tom i stället för att
Borsify gissar.

Relativ styrka används bara som ett bekräftelse- och sorteringslager efter att
aktien redan har klarat de ordinarie köpkraven. Den kan alltså inte ensam göra en
underkänd aktie till ett KÖPCASE.

För användaren visas detta på enkel svenska under "Jämfört med marknaden och sektorn",
med en förklaring av vad aktien och sektorn faktiskt gjort bättre eller sämre.


## v2.55.0 – Marknadslägesfilter

Borsify bedömer nu marknadsläget separat för varje marknad i den aktuella körningen.
Bedömningen bygger på:
- medianutvecklingen för aktierna på 1 månad,
- medianutvecklingen på 3 månader,
- hur stor andel av aktierna som faktiskt stiger.

Marknaden klassas som Stark, Neutral, Svag, Mycket svag eller För lite underlag.

Den viktigaste säkerhetsprincipen är asymmetrisk:
- en svag marknad kan höja kravet för att bli KÖPCASE,
- en stark marknad får aldrig sänka Borsifys vanliga köpkrav.

Vid Svag marknad höjs köpgränsen med:
- +2 poäng för 1–2 dagar,
- +3 poäng för 1 vecka–3 månader,
- +2 poäng för 1–5 år,
- +1 poäng för mycket lång sikt.

Vid Mycket svag marknad höjs kraven ytterligare till +4, +5, +3 respektive +2 poäng.

Om färre än fem aktier har användbar kursdata ändras inga köpkrav. Borsify visar då
att underlaget är för litet.

Aktier som klarar det vanliga köpfiltret men stoppas av ett svagt marknadsläge kan
visas under Nära köpsignal. Där förklaras att aktien i sig klarar grundkraven men
behöver ett högre betyg så länge marknaden är svag.

Marknadsläget är ett riskfilter och inte en prognos. Trösklarna är konservativa
heuristiker och ska senare utvärderas mot sparade rekommendationsutfall innan de
kalibreras.


## v2.56.0 – Borsify lär av gamla rekommendationer

Borsify kan nu sammanfatta vad som faktiskt hänt efter tidigare frysta
rekommendationer. Syftet är att hitta återkommande styrkor och svagheter i
Borsifys egna case – utan att automatiskt optimera modellen på ett litet sample.

Under Historiska tester → Tidigare rekommendationer finns nu
"Vad har Borsify lärt sig hittills?".

Borsify kan jämföra mogna utfall efter:
- den bedömning/gate som fanns när caset skapades,
- scoregrupp,
- hur bra underlaget var,
- sektor,
- modellversion.

Varje historisk grupp måste ha minst 8 mogna utfall innan den får användas i en
jämförelse. Grupper med färre observationer visas som "För få utfall".

Om minst två tillräckligt stora grupper skiljer sig tydligt kan Borsify beskriva
ett möjligt historiskt mönster, till exempel att en viss scoregrupp hittills haft
bättre medianutfall än en annan. Texten säger uttryckligen att detta är en
observation och inte ett bevis på framtida avkastning.

Borsify kontrollerar också om högre frysta scoregrupper faktiskt tenderat att ge
bättre utfall. Om högre score i stället konsekvent följts av sämre utfall visas
en varning.

### Ingen efterhandskonstruktion

Lärandet använder bara data som fanns i den frysta rekommendationen när den
skapades. Om en ny Borsify-funktion inte fanns i äldre snapshots kan den inte
testas retroaktivt med dagens värden. Saknade historiska uppgifter lämnas saknade.

Från v2.56 sparas dessutom fler befintliga datafält i nya snapshots, bland annat
1/3/6-månadersutveckling, handelsaktivitet, RSI, avstånd till lång trend,
datatäckning samt fler kvalitets-/riskmått. Detta förbättrar möjligheten att göra
mer detaljerade analyser när dessa rekommendationer senare har hunnit mogna.

### Ingen automatisk viktoptimering

v2.56 ändrar inte modellvikter, köpgränser eller scoring automatiskt. Resultaten
är deskriptiv kvalitetskontroll. En eventuell framtida ändring ska kräva större
sample, stabilt mönster över tid och separat historisk validering.


## v2.57.0 – Case Quality Program

Den här releasen fokuserar på kvaliteten i beslutsunderlaget i stället för att
lägga till ännu en köpsignal.

Ett högt Borsify-betyg räcker inte längre för att få en plats i Top 3. Caset måste
också klara en separat kontroll av hur väl analysen är underbyggd.

### Case Readiness 0–100

Case Readiness mäter fem saker:

1. **Datagrund**
   - verifierad marknadsdata,
   - hur komplett bolagsdatan är,
   - hur många av de viktigaste datapunkterna för vald tidshorisont som faktiskt finns.

2. **Oberoende bekräftelser**
   - flera olika delar av analysen måste peka åt samma håll.
   - exakt vilka delar som används beror på om horisonten är dagar, månader eller år.

3. **Tydlig riskbild**
   - allvarliga riskflaggor stoppar caset,
   - för kortare handel måste Borsify kunna räkna fram en användbar riskplan från
     verklig kurshistorik. Saknas den får caset inte en Top-3-plats.

4. **Tydlig investeringstes**
   - Borsify kontrollerar att det finns mer än ett konkret skäl som faktiskt bär caset.

5. **Aktuell kursdata**
   - gammal eller odaterad kursdata sänker kvaliteten på beslutsunderlaget.

### Separat från avkastningsprognosen

Case Readiness är inte en prognos för hur mycket aktien ska stiga. Ett bolag kan ha
ett högt aktiebetyg men ett svagt beslutsunderlag, eller ett mycket bra underlag men
ändå inte vara tillräckligt attraktivt för köp.

För Top 3 krävs minst 60/100 i Case Readiness och inga hårda underlagsstopp.
Från 78/100 märks caset som "Mycket väl underbyggt".

Om inget case klarar både köpkraven och underlagskontrollen visar Borsify hellre en
tom Top-3-lista än fyller den med ett sämre case.

### Vad användaren ser

Varje rekommendationskort visar:
- hur väl caset är underbyggt,
- styrkorna i underlaget,
- luckor som fortfarande finns,
- antal centrala datapunkter som finns,
- hur många separata delar som bekräftar caset.

Detta är en konservativ kvalitetskontroll. Gränsen 60 och poängfördelningen är
heuristiker och ska utvärderas mot sparade framtida rekommendationsutfall innan
de kalibreras.


## v2.58.0 – Fundamental Inflection Engine 2.0

Den här releasen försöker förbättra frågan "Vad håller faktiskt på att förändras i
bolaget?" i stället för att bara läsa statiska nyckeltal.

Borsify skiljer nu tydligare mellan två typer av information:

- **observerad utveckling i bolaget** – försäljning, marginaler, vinst, fritt
  kassaflöde och skuld/nettoskuld när data finns,
- **analytikernas prognoser** – ändrade vinstestimat och revisionsbalans.

Det är viktigt eftersom höjda analytikerprognoser inte får dölja att den faktiska
verksamheten försämras.

### Bred fundamental förbättring/försämring

För de djupanalyserade kandidaterna räknar Borsify hur många oberoende operativa
delar som förbättras respektive försämras. När flera delar rör sig åt samma håll
klassas utvecklingen exempelvis som:

- Bred fundamental förbättring
- Övervägande förbättring
- Blandad fundamental utveckling
- Övervägande försämring
- Bred fundamental försämring
- För lite operativ förändringsdata

En bred fundamental försämring kan sänka ett annars godkänt djupcase till
"Kräver extra kontroll". Positiva analytikerestimat får inte rädda ett sådant case.

### Mer kvartalsdata

När Yahoo tillhandahåller uppgifterna använder v2.58 även kvartalsbalansräkningen
för att mäta förändring i skuld och nettoskuld. Den följer också hur stor andel av
de senaste kvartalen som haft positiv försäljningstillväxt respektive positivt
fritt kassaflöde.

Saknade balans- eller kvartalsuppgifter förblir saknade. Borsify konstruerar inte
historik från dagens värden.

### Konfliktkontroll

Borsify markerar nu uttryckligen när:
- analytikernas prognoser förbättras samtidigt som flera observerade delar av
  verksamheten försämras, eller
- verksamheten förbättras samtidigt som analytikernas prognoser ännu är svaga.

Den första konflikten är särskilt viktig och ger ett avdrag i förändringsbedömningen.

Detta är fortfarande regelbaserade heuristiker. De nya förändringsmåtten är inte
bevisade som framtida avkastningssignaler och ska senare utvärderas mot den
frysta rekommendationshistoriken.


## v2.59.0 – Vinstkvalitet och kassaflöde

Borsify kontrollerar nu om redovisad vinst faktiskt stöds av pengar som kommer in
i verksamheten.

För djupanalyserade långsiktiga case mäts bland annat:
- kassaflöde från verksamheten i förhållande till redovisad vinst,
- fritt kassaflöde i förhållande till redovisad vinst,
- om det senaste året avviker negativt från flerårsmönstret,
- hur stor påverkan förändringar i rörelsekapitalet har på kassaflödet,
- om kundfordringar växer snabbare än försäljningen,
- om lager växer snabbare än försäljningen.

Borsify klassar underlaget som Stark vinstkvalitet, Normal vinstkvalitet,
Kräver kontroll, Svag vinstkvalitet eller För lite underlag.

Svag vinstkvalitet kan sänka ett annars godkänt djupcase till "Kräver extra
kontroll". Saknade redovisningsrader lämnas saknade och fylls inte med antaganden.

Detta är ett kvalitetsfilter, inte en avkastningsprognos. Trösklarna är
regelbaserade heuristiker och ska senare utvärderas mot frysta utfall.


## v2.60.0 – Datakoll och färskhetsgräns

Borsify visar nu ett separat datapass för rekommendationer. Syftet är att göra det
svårare för ett gammalt eller ofullständigt underlag att se mer säkert ut än det är.

Datakollen visar:
- källa för bred marknads- och bolagsdata: Yahoo Finance via yfinance,
- senaste kursdatum,
- när Borsify hämtade bolagsdatan,
- om rapportdatum faktiskt är verifierat i djupanalysen,
- varningar för låg datatäckning eller delvis verifierad data.

Viktigt: hämtningstiden för bolagsdata är inte samma sak som rapportdatum. I den
breda scanningen säger Borsify därför uttryckligen att rapportdatum inte är
verifierat i stället för att låta en färsk hämtningstid se ut som färsk rapportdata.

Universe QC har också skärpts:
- kursdatum 0–4 kalenderdagar gammalt behandlas normalt som färskt,
- 5–7 dagar ger en kvalitetsvarning,
- mer än 7 dagar gammal kursdata hårdexkluderas från ranking.

Kalenderdagar används eftersom Borsify inte har en fullständig handelskalender för
alla 15 marknader. Gränsen är därför medvetet generös för helger och enstaka
helgdagar. Den ska inte beskrivas som en exakt börsdagskontroll.


## v2.61.0 – Focused Borsify

Den här releasen tar bort konkurrens om uppmärksamheten på startsidan och skjuter
upp dyra analyser tills användaren faktiskt behöver dem.

### Första skärmen

Överblick börjar nu med "Dagens bästa möjligheter" och visar högst tre kandidater.
Varje kort fokuserar på:
- varför aktien är intressant,
- vad användaren bör kontrollera före beslut,
- senaste kursdatum,
- status för datakollen.

De fyra separata listorna för olika tidshorisonter finns kvar, men ligger bakom
"Visa bästa köp efter tidshorisont". Portföljens säljkontroll ligger också bakom
en expander. Funktionaliteten är alltså kvar utan att konkurrera med huvuduppgiften.

### Riktig sidnavigation i stället för fem Streamlit-tabs

De fem huvudvyerna använder nu en horisontell sidväljare. Bara den valda sidans
kod körs. Detta är viktigt eftersom Streamlit-tabs normalt beräknar innehållet i
alla tabs även när användaren bara tittar på en.

### Djupanalys körs först i Upptäck

Före v2.61 byggdes både den långsiktiga djupanalysen och den kortsiktiga
fördjupningen innan huvudnavigationen visades.

Från v2.61 körs dessa Yahoo-baserade fördjupningar först när användaren väljer
Upptäck. Överblick, Bevakning, Analysera och Metod slipper därför dessa
djupförfrågningar.

Rekommendationshistoriken fryser bara de djupa finalister som faktiskt analyserats.
Det är en medveten avvägning: vanlig användning blir lättare, medan point-in-time-
historiken för djupmodeller fylls när Upptäck används. Den schemalagda scannerns
beteende är inte ändrat i denna release.

Detta är en verifierad arkitekturförändring, men den faktiska förbättringen i
sekunder på Streamlit/Yahoo måste mätas i live-miljön innan en prestandavinst i
procent eller sekunder kan påstås.


## v2.62.0 – Färre siffror, tydligare beslut

Borsify har många interna delmodeller, men användaren ska inte behöva tolka alla
deras 0–100-tal samtidigt.

Från v2.62 följer rekommendationsvyerna en tydligare hierarki:

1. **Borsifys huvudbetyg** – den enda stora numeriska score som visas först.
2. **Underlag** – visas i första hand som en begriplig status, till exempel
   "gott", "användbart men inte komplett" eller "begränsat".
3. **Beslut och motargument** – varför caset är intressant, varför nu, vad som
   talar emot och vad som skulle ändra bedömningen.
4. **Delpoäng** – relativ styrka, bekräftelseantal, detaljerad confidence,
   value-trap-risk och andra interna mått finns kvar bakom "Visa..."-sektioner.

Ingen scoringlogik eller gate har tagits bort i denna release. Förändringen är
avsiktligt en UX-förenkling: samma analyser arbetar under huven, men färre siffror
konkurrerar om användarens uppmärksamhet.

På de långsiktiga djupcasen har den tidigare raden med INVEST, value-trap-risk,
inflection, mispricing och confidence ersatts av ett huvudbetyg och en enkel
underlagsstatus. Delmåtten finns kvar under "Visa delbedömningar".

På kortsiktiga case visas inte längre score, confidence, relativ styrka och antal
bekräftelser som fyra parallella huvudmått. Huvudbetyget visas först och övriga
mått är fördjupning.

Case Readiness finns också kvar internt och i detaljvyn, men huvudkortet visar
dess begripliga status i stället för ytterligare ett 0–100-tal.


## v2.63.0 – Snabbare bred scanning

Den breda scanningen har byggts om för att undvika onödiga bolagsdata-anrop.

### Prisdata först

Tidigare startade Borsify Yahoo-hämtning av bolagsdata för samtliga valda tickers
samtidigt som kurshistoriken hämtades. Det innebar att en trasig, gammal eller
oanvändbar ticker kunde orsaka ett dyrt fundamental-anrop trots att aktien senare
ändå skulle exkluderas.

Från v2.63 sker scanningen i två tydliga steg:

1. Borsify hämtar kurshistoriken i bulk och gör den hårda kvalitetskontroll som
   redan kan avgöras från pris, kursdatum och historiklängd.
2. Bara aktier som klarar denna första kontroll får gå vidare till Yahoo
   `get_info` för bolagsdata.

Detta ändrar inte vilka prisgiltiga aktier som får fundamentaldata och är därför
inte en ny rankingheuristik.

### 24-timmars beständig cache för bolagsdata

Fundamentala Yahoo-fält förändras normalt inte minut för minut. Borsify sparar
därför ett lyckat fundamental-svar i lokal SQLite-cache i upp till 24 timmar.

Detta kompletterar Streamlits vanliga minnescache. Den beständiga cachen kan
fortfarande användas efter en vanlig `st.cache_data.clear()` och minskar därför
risken att samma hundratals `get_info`-anrop görs om flera gånger samma dag.

Kursdata har fortfarande den betydligt kortare cachen och kan uppdateras separat.
24-timmarsgränsen gäller alltså bolagsdata, inte aktiekursen.

### Mätning i appen

Datastatus visar nu faktisk tid i den aktuella körningen för:
- kursdelen,
- bolagsdatadelen,
- antal träffar i den beständiga cachen,
- antal nya Yahoo-anrop,
- antal aktier som stoppades redan på kursdata.

Dessa siffror ska användas för nästa optimeringsbeslut. Borsify påstår inte någon
procentuell prestandaförbättring innan live-mätningar finns.

### Begränsning

En kall första scanning av ett stort och helt giltigt universum behöver fortfarande
hämta bolagsdata för många aktier. v2.63 reducerar upprepade anrop och slösade
anrop till ogiltiga tickers, men löser inte hela cold-start-problemet.


## v2.64.0 – Validering före tvåstegsscanning

v2.64 kapar ännu inga fundamental-anrop utifrån en price-only-gallring.

I stället simulerar Borsify vad som hade hänt om en billig första gallring fått
välja vilka aktier som skulle gå vidare till full bolagsdata.

### Hur simuleringen fungerar

Den billiga gallringen använder bara sådant som redan finns i kurshistoriken:
- 1, 3 och 6 månaders kursutveckling,
- avstånd till 52-veckorstopp,
- RSI,
- volymkvot,
- avstånd till 200-dagars medelvärde,
- ungefärlig handelsomsättning.

För att minska risken att bara välja momentumaktier byggs kandidatpoolen som en
union av flera olika prislinser:
- trend,
- rekyl,
- möjlig vändning,
- stabilitet.

Standardtestet använder ungefär 60 % av det fulla universumet, dock minst 80
aktier när universumet är tillräckligt stort.

### Vad mäts?

Efter att den vanliga fulla Borsify-analysen är klar jämförs den simulerade
kandidatpoolen med:
- de fem högst rankade aktierna i huvudmodellen,
- Top 3 för 1–2 dagar,
- Top 3 för 1 vecka–3 månader,
- Top 3 för 1–5 år,
- Top 3 för mycket lång sikt.

Borsify visar sedan hur många av dessa slutliga toppkandidater som en billig
första gallring hade behållit.

### Ingen aktivering efter en enda bra körning

Resultatet sparas per dag och marknad i SQLite.

Borsify rekommenderar inte ens ett kontrollerat aktiveringstest förrän minst fem
separata körningar finns. Dessutom krävs:
- minst 98 % genomsnittlig träff i de senaste körningarna,
- ingen enskild körning under 95 %.

Även när detta uppfylls är gallringen fortfarande inte automatiskt aktiverad.

Det här är medvetet konservativt. En snabbare app är inte bättre om den missar ett
starkt investeringscase.


## v2.65.0 – Liquidity & Execution Guard

Den här releasen gör de korta köpcasen mer praktiskt användbara.

Borsify kontrollerar nu normal daglig handelsomsättning innan en aktie får visas
som Top 3 för 1–2 dagar eller 1 vecka–3 månader.

### Hårda miniminivåer

För 1–2 dagar:
- under 2 MSEK i normal daglig handel stoppas,
- 2–10 MSEK märks som tunnare handel,
- över 10 MSEK behandlas som godtagbar handel.

För 1 vecka–3 månader:
- under 1 MSEK stoppas,
- 1–5 MSEK märks som tunnare handel,
- över 5 MSEK behandlas som godtagbar handel.

Om omsättningsdata saknas stoppas korta Top-3-case i stället för att Borsify gissar.

Fleråriga case hårdfiltreras inte av samma kortsiktiga likviditetsgränser.

### Viktig begränsning

Borsify har fortfarande dagsdata från Yahoo. Den kan därför inte verifiera:
- aktuell bid/ask-spread,
- orderboksdjup,
- antal avslut i realtid,
- faktisk slippage.

Appen säger detta uttryckligen. 1–2-dagarsvyn beskrivs nu som en kortsiktig
dagsdatabaserad signal och inte som en intradagssignal.

Detta är en grov exekveringskontroll, inte en garanti för att en viss orderstorlek
kan genomföras utan pris påverkan.


## v2.66.0 – Kritisk kraschfix + färskare "Varför nu?"

### Kritisk kraschfix

Efter v2.61 flyttades huvudnavigationen och vissa dyra analyser. I samband med
detta låg en gammal rad kvar som byggde marknadsjämförelsen med variablerna
`idx`, `benchmark_name` och `benchmark_symbol` utan att de längre skapades i
`main()`.

Det gav ett `NameError` och stoppade hela appen efter scanningen.

v2.66 skapar nu marknadens benchmark-konfiguration explicit efter marknadsvalet
och hämtar indexsnapshoten innan texten använder den. Samma variabler finns även
för sidan med historiska tester.

Ett regressionstest kontrollerar ordningen så att samma typ av refaktorbugg inte
ska kunna passera testsviten igen.

### "Varför nu?" kräver nu tidsstämplad nyhet

Tidigare kunde en Yahoo-rubrik klassificeras som möjlig katalysator även när
Borsify inte kunde verifiera hur gammal rubriken var.

Från v2.66:
- publiceringsdatum och källa sparas när Yahoo tillhandahåller dem,
- en rubrik utan verifierbart datum får inte skapa ett positivt "Varför nu?",
- rubriker äldre än 30 dagar räknas inte som aktuell katalysator,
- rubriker 15–30 dagar gamla får lägre bevisstyrka,
- färska negativa rubriker kan fortfarande stoppa ett positivt katalysatorbudskap,
- rubriker är alltid bara en ledtråd och ska verifieras i originalkällan.

Detta minskar risken att gammal nyhetsinformation presenteras som något som händer
"just nu".

### Språk

Några kvarvarande tekniska ord i djupcaset har också förenklats. Bland annat
visas inte längre "avkastningshurdle" i användartexten.


## v2.67.0 – Ticker, flagga och land överallt

Aktier som visas som rekommendationer eller kandidater får nu en gemensam identitet:

`🇸🇪 Volvo B · VOLV-B.ST · Sverige`

Det gör det enklare att:
- söka upp rätt aktie direkt,
- skilja mellan bolag med liknande namn,
- förstå vilken marknad/notering Borsify analyserar,
- undvika att råka söka på fel notering i ett annat land.

Regeln används i startsidans bästa möjligheter, Top 3 efter tidshorisont,
kortsiktiga och långsiktiga fördjupningar samt övriga kandidatlistor.

Land härleds deterministiskt från tickerformatet för Borsifys nuvarande marknader.
Tickers utan känd utländsk suffix behandlas som USA enligt samma befintliga
marknadslogik som används i resten av appen.

### Tydligare "Varför nu?"

När en möjlig katalysator har ett identifierbart underlag visar Borsify nu även
vilken typ av underlag det är och vilken källa analysen bygger på, exempelvis:

`Underlag: Daterad extern rubrik · källa: Reuters`

eller:

`Underlag: Rapporterade siffror och estimat · källa: Bolagsdata/analytikerdata`

Detta ändrar inte katalysatorscoringen. Syftet är att göra slutsatsen lättare att
granska och tydligare skilja en extern daterad rubrik från rapporterade bolagssiffror.


## v2.68.0 – Filtrera på land och aktiepris

Land och aktiepris är nu förstklassiga sökfilter i sidopanelen.

### Land

Användaren kan välja ett eller flera länder i ett multiselect-filter där varje
land visas med flagga. Exempel:

- 🇸🇪 Sverige
- 🇺🇸 USA
- 🇩🇪 Tyskland

Landfiltret tillämpas redan innan Yahoo-scanningen startar. Om användaren i ett
globalt universum bara väljer Sverige och USA behöver Borsify alltså inte ens
börja hämta övriga länder i den körningen.

Om inget land är valt startar ingen scanning.

### Pris per aktie

Användaren kan ange:

- Pris från (SEK)
- Pris till (SEK)

0 betyder ingen gräns.

För utländska aktier används Borsifys befintliga valutaomräkning till `Pris SEK`.
Det gör att ett globalt prisfilter blir jämförbart. Ett filter på exempelvis
100–300 SEK betyder alltså samma ekonomiska prisintervall oavsett om aktien
ursprungligen handlas i USD, EUR, DKK eller annan stödd valuta.

Om prisfilter används och Borsify inte kan räkna fram ett SEK-pris exkluderas
aktien i stället för att ett lokalt pris felaktigt jämförs med SEK-gränsen.

### Övrigt

Sidotexten om cache har rättats. Den visar nu att kurser normalt cachas 15 minuter
och att bolagsdata kan återanvändas från den beständiga 24-timmarscachen.


## v2.70.0 – Enklare kombinerad aktiesökning

De viktigaste sökvalen finns nu samlade i samma enkla flöde:

1. Typ av case
2. Tidshorisont
3. Marknad/land
4. Pris per aktie i SEK

"Mitt mål" heter nu "Typ av case" eftersom det bättre beskriver vad användaren
faktiskt väljer, till exempel kortsiktigt köpläge, utdelningsaktier eller billiga
kvalitetsbolag.

### Tidshorisont

Användaren kan välja:
- Alla tidshorisonter
- 1–2 dagar
- 1 vecka–3 månader
- 1–5 år
- Mycket lång sikt

Borsify bygger inte en ny separat modell för detta. Sökningen använder de
befintliga horizon-scorerna och kombinerar vald tidshorisont med den valda
case-typen för att prioritera resultaten.

Horisonten är därför en sökprioritering. Den ersätter inte Buy Quality Gate,
datakontroll, likviditetskontroll eller andra befintliga säkerhetsregler.

### Din sökning

Ett kompakt fält "Din sökning" visar de aktiva huvudvalen:
- case-typ,
- tidshorisont,
- land,
- prisintervall.

Avancerade filter ligger fortfarande separat bakom "Fler filter", så den normala
användaren behöver inte möta fler val än nödvändigt.

## v2.71.0 – Multi-lens Finalist Selection

Djupanalysen startar inte längre enbart från de högsta INVEST-poängen. Den lilla finalistpoolen behåller de starkaste INVEST-casen men reserverar även plats för kandidater som sticker ut i redan befintliga linser: bolagskvalitet, mycket lång ägarhorisont, möjlig vändning och värdering. Svaga alternativ får inte en plats bara för att de råkar vara bäst i en svag grupp; rimliga miniminivåer används och tomma platser fylls med befintlig långsikts-/INVEST-rankning.

Detta skapar ingen ny köp-score och ökar inte normal storlek på deep-scan-poolen. Urval till djupanalys är inte en köprekommendation; befintliga data-, value-trap-, vinstkvalitets-, inflection-, mispricing-, scenario- och catalyst-kontroller avgör fortfarande slutlig ordning och kvalitet.


## v2.72.0 – Deep Selection Audit

Varje aktie som släpps in i den långsiktiga djupanalysen fryser nu varför den kom med.
Borsify sparar en stabil urvalsnyckel för den primära vägen (INVEST, kvalitet, mycket lång
sikt, vändning, värdering eller flerårig profil) samt vilka övriga befintliga linser som var
starka vid urvalstillfället. Metadata följer med in i rekommendationshistorikens snapshot.

Det finns också en deskriptiv analysfunktion som kan jämföra senare utfall per urvalsväg.
Den ändrar aldrig vikter automatiskt. Små stickprov ska inte användas för slutsatser om att
en urvalsväg är bättre; syftet är spårbarhet och framtida validering, inte självlärande heuristik.

## v2.73.0 – Finalist Coverage Test

Borsify kan nu validera om den långsiktiga deep-scan-poolen på sex kandidater är lagom stor i stället för att ändra den på känsla.

Valideringen jämför poolstorlekarna 4, 6, 8 och 10 mot **en och samma redan djupanalyserade referenskörning**. Därmed behöver en referenspool på exempelvis tio kandidater bara hämtas en gång; analysen simulerar därefter vilka av referensens starkaste slutcase som hade överlevt mindre finalistpooler.

Mätningen visar bland annat:
- hur stor andel av referensens bästa djupcase varje poolstorlek fångar,
- vilka starka referenscase som missas,
- hur många extra deep-anrop 8 respektive 10 innebär jämfört med dagens pool på 6.

En separat aggregatfunktion kräver minst fem oberoende körningar, minst 98 % genomsnittlig täckning och ingen körning under 95 % innan en poolstorlek ens markeras som tillräckligt stabil för att övervägas. Poolstorleken ändras **inte automatiskt**.

Detta är en utvecklings-/valideringsmotor och körs inte automatiskt i det vanliga användarflödet. Borsify fortsätter därför med poolstorlek 6 tills faktisk mätdata motiverar något annat.


## v2.74.0 – Catalyst Quality / Varför nu? 2.0

- Hindrar dubbelräkning där samma fundamentala inflektion tidigare kunde vara både förändringsstöd och separat katalysatorstöd.
- Fundamental förbättring, skuldminskning och kassaflödesvändning får fortfarande förklara varför caset är aktuellt, men räknas inte som en oberoende femte pelare.
- Separat katalysatorstöd kräver nu en färsk, daterad positiv extern signal från en namngiven källa.
- UI visar tydligare källkontroll och om Varför nu-underlaget faktiskt är oberoende från övrig analys.
- Rubrikdata är fortfarande triage: originalkällan måste verifieras innan användaren agerar.

## v2.76 – Fundamental Data Confidence

Djupcase får nu en separat datakontroll av själva fundamentaunderlaget. Borsify kontrollerar om resultat-, kassaflödes- och balansdata faktiskt finns, om kvartalsserier finns och hur gammal den senaste verifierbara rapportperioden är. Ett case med för gammal eller overifierbar fundamental datagrund kan inte bli toppcase bara för att övriga scores ser starka ut. Kontrollen är en kvalitetsgrind, inte en ny investeringsscore.


## v2.77 – Estimate Revision Quality

Analytikerrevideringar vägs nu efter verifierbar täckning. När Yahoo lämnar antal analytiker skiljer Borsify mellan bred, användbar, tunn och mycket tunn täckning. Om total täckning saknas kan faktisk revisionsaktivitet användas som ett försiktigt tecken på att analytiker finns, men Borsify hittar aldrig på ett analytikerantal. Estimat med tunn eller oklar täckning får lägre påverkan på inflektionsbedömningen, och helt overifierbar täckning får inte flytta scoren. UI visar täckningsstatus och antal när de faktiskt finns.

## v2.78 – Recommendation Outcome Quality

Rekommendationshistoriken mäter nu mer än rå kursuppgång. Mogna utfall kan även sparas med relevant jämförelseindex, utveckling mot index, bästa och sämsta utveckling under mätperioden samt antal handelssessioner till periodens bästa nivå. Sverige jämförs exempelvis med OMXS30, USA med S&P 500 och globalt urval med VT. Learning Engine använder indexrelativt utfall först när hela den valda utfallsgruppen har sådan data; annars används rå kursutveckling så gamla och nya mätmetoder inte blandas. Historiken är fortsatt deskriptiv och ändrar inte modellvikter automatiskt.


## v2.79 – Recommendation Failure Analysis

Tydligt svaga historiska rekommendationer får en försiktig efterhandsdiagnos baserad enbart på den data som frystes när rekommendationen skapades. Diagnosen kan peka ut varningssignaler som värdefälla, få oberoende stöd, svag fundamentaldatakvalitet, svag vinstkvalitet eller ett svagt varför-nu. Den försöker inte bevisa vad som orsakade kursutfallet och rekonstruerar aldrig saknad historik med dagens data.

## v2.80 – Failure Pattern Aggregation

Borsify jämför nu hur ofta frysta varningssignaler förekommer i tydligt svaga utfall mot hur ofta samma signal uttryckligen saknas i jämförelsegruppen. Analysen använder alltid en gemensam utfallsgrund för hela vald period: indexrelativ utveckling endast när alla case har sådan data, annars rå kursutveckling. Saknade historiska fält räknas inte som att varningen saknades. Ett möjligt återkommande mönster kräver minst fem case både med och utan signal, minst tre misslyckanden bland exponerade case och minst 15 procentenheters högre misslyckandegrad. Resultaten är deskriptiva och får inte automatiskt ändra modellvikter eller köpgränser.
