from __future__ import annotations

import pandas as pd

# Explicit model-relevant release register. This is documentation/governance only;
# it does not mutate model parameters and is deliberately separate from runtime data.
MODEL_CHANGE_LOG = [
    {"Version": "3.26.0", "Förändring": "News Surprise & Price Response", "Typ": "Produktionsförklaring", "Status": "Införd + valideras", "Motivering": "Skiljer explicit förväntningsöverraskning från vanlig positiv/negativ rubrik och mäter observerad kursrespons utan nytt score, uppfunnen konsensus eller kausalitetsanspråk."},
    {"Version": "3.25.0", "Förändring": "News Flow Monitor 2.0", "Typ": "Produktionsförklaring", "Status": "Införd + valideras", "Motivering": "Följer serier av deduplicerade nyheter, förändrad riktning och hur kursen absorberar flera separata händelser utan nytt score eller kausalitetsanspråk."},
    {"Version": "2.91.0", "Förändring": "Sector-aware Valuation", "Typ": "Produktionslogik", "Status": "Införd", "Motivering": "Värderingsmått ska tolkas olika mellan branscher."},
    {"Version": "2.92.0", "Förändring": "Expectation Change Engine", "Typ": "Produktionslogik", "Status": "Införd", "Motivering": "Förändrade förväntningar används i varför-nu-bedömningen."},
    {"Version": "2.98.0", "Förändring": "Post-Report Drift", "Typ": "Produktionssignal", "Status": "Införd + valideras", "Motivering": "Rapportreaktion och efterföljande drift följs point-in-time."},
    {"Version": "2.99.0", "Förändring": "Earnings Quality 2.0", "Typ": "Produktionssignal", "Status": "Införd + valideras", "Motivering": "Kassaflöde och accrual-risk kompletterar redovisad vinst."},
    {"Version": "3.00.0", "Förändring": "Investment Discipline", "Typ": "Produktionssignal", "Status": "Införd + valideras", "Motivering": "Kapitalbindning och effektiv tillväxt granskas separat."},
    {"Version": "3.01.0", "Förändring": "Evidence Families", "Typ": "Produktionslogik", "Status": "Införd + valideras", "Motivering": "Närliggande signaler ska inte räknas som oberoende bevis."},
    {"Version": "3.02.0", "Förändring": "12–1 Momentum", "Typ": "Produktionssignal", "Status": "Införd + valideras", "Motivering": "Längre momentum separeras från senaste månadens rörelse."},
    {"Version": "3.03.0", "Förändring": "Idiosyncratic Volatility", "Typ": "Risk/motbevis", "Status": "Införd + valideras", "Motivering": "Bolagsspecifik volatilitet används som risk, aldrig som pluspoäng."},
    {"Version": "3.05.0", "Förändring": "Signal Governance", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Signaler kan granskas för behåll/nedtoning/avveckling utan automatisk ändring."},
    {"Version": "3.06.0", "Förändring": "Champion–Challenger", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Föreslagna modellvarianter måste slå champion parallellt innan manuell produktionsgranskning."},
    {"Version": "3.07.0", "Förändring": "Prospective Challenger Registry", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Challengers låses före nya utfall och får bara bedömas på senare point-in-time-case innan manuell promotion."},
    {"Version": "3.08.0", "Förändring": "Model Promotion Protocol", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Promotion kräver prospektiva resultat, rangordning, regimrobusthet, datatäckning och dokumenterad rollback innan manuell releaseprövning."},
    {"Version": "3.09.0", "Förändring": "Production Model Registry + Rollback History", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Faktisk champion, fingerprint, promotionsbeslut och rollbackhändelser registreras append-only för full spårbarhet."},
    {"Version": "3.10.0", "Förändring": "Model Health Monitor", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Champion följs efter driftsättning med fasta kontroller för utfall, rangordning, data, signalbeteende och marknadslägen; rollback kräver manuell prövning."},
    {"Version": "3.11.0", "Förändring": "Root Cause Diagnostics", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "När modellhälsan försämras isoleras diagnostiska kandidater i signaler, marknader, sektorer, regimer och datakvalitet utan automatisk modelländring."},
    {"Version": "3.12.0", "Förändring": "Drift Attribution / Failure Cohorts", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Fördefinierade typer av misslyckade case jämförs mot övriga och mot föregående fönster för att lokalisera koncentrerad modellförsämring utan automatisk ändring."},
    {"Version": "3.13.0", "Förändring": "Case Archetypes / Interaction Diagnostics", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Fördefinierade tvåsignalskombinationer jämförs mot case med exakt en av signalerna för att hitta möjlig extra kombinationseffekt utan automatisk modelländring."},
    {"Version": "3.14.0", "Förändring": "Regime-aware Archetypes", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Fördefinierade signalarketyper testas separat i frysta marknadslägen för att upptäcka regimberoende och undvika generella regler som bara fungerar i ett börsklimat."},
    {"Version": "3.15.0", "Förändring": "Regime-aware Selection Policy", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Låsta policyhypoteser testar om riskfyllda case i svag marknad historiskt hade bättre utfall när de uppfyllde ett extra beviskrav. Diagnostiken ändrar inga köpgränser eller regler automatiskt."},
    {"Version": "3.16.0", "Förändring": "Prospective Policy Registry", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Policyhypoteser förregistreras med stabila definitioner och får endast utvärderas på nya point-in-time-case från registreringsversionen och framåt innan manuell policygranskning."},
    {"Version": "3.17.0", "Förändring": "Policy Promotion Protocol", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Policyförändringar måste klara fem separata grindar: prospektivt stöd, utfall/kalibrering, regimrobusthet, datatäckning och dokumenterad rollback innan ett manuellt releasebeslut ens får övervägas."},
    {"Version": "3.18.0", "Förändring": "Production Policy Registry + Rollback History", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Aktiv urvalspolicy, exakt definitionsfingerprint, manuella promotionsbeslut och rollbackhändelser registreras append-only. Runtime måste matcha registrerad policy innan den betraktas som driftsatt."},
    {"Version": "3.19.0", "Förändring": "Policy Health Monitor", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Aktiv policy följs efter driftsättning för urvalsgrad, utfall, missade vinnare, datatäckning och regimrobusthet utan automatisk rollback."},
    {"Version": "3.20.0", "Förändring": "Policy Root Cause Diagnostics", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Vid policyförsämring skiljs möjliga orsaker mellan för hård filtrering, missade vinnare, regimproblem, case-typer och databrister. Diagnostiken är associativ och ändrar aldrig policyn automatiskt."},
    {"Version": "3.21.0", "Förändring": "Evidence Maturity Dashboard", "Typ": "Modellstyrning", "Status": "Införd", "Motivering": "Signaler, challengers och policyer samlas i en konservativ mognadsvy som tydligt skiljer historiskt stöd från prospektiv evidens och manuell produktionsgranskning."},
    {"Version": "3.22.0", "Förändring": "Why Now Evidence Engine", "Typ": "Produktionsförklaring", "Status": "Införd + valideras", "Motivering": "Färska förändringar samlas utan nytt score: rapporterade siffror/förväntningar, färsk post-report-bekräftelse och oberoende katalysator hålls isär och motbevis visas direkt."},
    {"Version": "3.23.0", "Förändring": "Fresh Change Detector 2.0", "Typ": "Produktionsförklaring", "Status": "Införd + valideras", "Motivering": "Nya förbättringar och försämringar i kvartal, kassaflöde och estimat skiljs från redan etablerad styrka."},
    {"Version": "3.24.0", "Förändring": "News Impact Engine", "Typ": "Produktionsförklaring", "Status": "Införd + valideras", "Motivering": "Färska rubriker kopplas konservativt till observerad kursreaktion och möjlig underreaktion utan kausalitetsanspråk eller nytt score."},
]


def model_change_log_table() -> pd.DataFrame:
    return pd.DataFrame(MODEL_CHANGE_LOG).copy()
