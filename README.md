# Borsify v2.13.0

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
