# Borsify v2.1.0


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
