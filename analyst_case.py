"""Evidence-grounded case text; no invented catalysts, targets or report claims."""
import math
from purchase_consistency import number

def analyst_case(row):
    facts = []
    for key, label in [("Omsättningstillväxt", "omsättningstillväxt"), ("Vinstmarginal", "vinstmarginal"), ("FCF-yield", "fritt kassaflöde/börsvärde")]:
        value = number(row.get(key))
        if math.isfinite(value):
            facts.append(f"{label} {value:.1%}")
    pe = number(row.get("P/E"))
    if math.isfinite(pe):
        facts.append(f"P/E {pe:.1f}")
    thesis = "Observerade nyckeltal: " + "; ".join(facts) + "." if facts else "Verifierade verksamhetsmått saknas; en bolagsspecifik köptes kan ännu inte beläggas."
    date = str(row.get("Fundamental hämtad") or "okänd tidpunkt")
    for key, label in [("Omsättning CAGR", "årlig omsättningstillväxt över tillgänglig flerårshistorik"), ("FCF CAGR", "årlig tillväxt i fritt kassaflöde över tillgänglig flerårshistorik"), ("Positiv FCF-andel", "andel historiska år med positivt fritt kassaflöde")]:
        value = number(row.get(key))
        if math.isfinite(value):
            thesis += f" {label.capitalize()}: {value:.1%}."
    thesis += f" Källa: Yahoo Finance, hämtat {date}. Måtten kan avse olika perioder; hämtningstid är inte rapportdatum."
    sector = str(row.get("Sektor", "")) + " " + str(row.get("Bransch", ""))
    sector = sector.lower()
    if any(word in sector for word in ["construction", "industrial", "engineering"]):
        risk = "Kontrollera orderbok, projektmarginaler och rörelsekapital genom konjunkturen. Ett enskilt starkt kassaflödesår bevisar inte uthållighet."
    elif any(word in sector for word in ["technology", "software", "it services"]):
        risk = "Kontrollera återkommande intäkter, kundberoende och om rörelseresultatet omvandlas till kassaflöde. Generella kvalitetsmått verifierar inte dessa risker."
    else:
        risk = "Kontrollera hur uthållig vinsten är, skuldernas finansiering och kassaflödet i senaste rapporten. Dessa risker är inte undanröjda av ett högt modellbetyg."
    flags = str(row.get("Riskflaggor", "") or "")
    if flags.lower() not in {"", "—", "inga", "nan", "none"}:
        risk = flags + ". " + risk
    invalidation = "Ompröva när nästa rapport kommer: jämför omsättning, marginal och kassaflöde med samma period föregående år."
    margin = number(row.get("Vinstmarginal"))
    if math.isfinite(margin):
        invalidation += f" Nuvarande registrerade marginal är {margin:.1%}; en försämring kräver en förklaring."
    invalidation += " Nytt köp kräver att alla köpkrav fortfarande är uppfyllda."
    return thesis, risk, invalidation
