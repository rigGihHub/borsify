from __future__ import annotations
"""Translate current model risks into a conservative development roadmap."""
from typing import Any
import pandas as pd

ACTION_MAP={
"Retire/downweight-kandidater finns":("Granska och isolera skadliga signaler","Validera varje kandidat över horisonter/regimer och förbered manuell downweight/retire. Inga produktionsvikter ändras automatiskt.","MODEL_VALIDATION"),
"Aktiva datakällfel påverkar analyskedjan":("Återställ datakällornas robusthet","Fixa fel/circuit breakers, kör source-health och verifiera att berörda analyser åter får komplett data.","DATA_RELIABILITY"),
"Otillräcklig prospektiv PIT-historik":("Bygg mer prospektivt facit","Prioritera frysta snapshots och outcome-mognad. Lägg inte till nya signaler bara för att öka modellens komplexitet.","EVIDENCE"),
"Signaler med negativ observerad edge":("Utred negativ signal-edge","Kontrollera datakvalitet, kohorter och marknadsregimer innan manuell kill/downweight-bedömning.","MODEL_VALIDATION"),
"Signalredundans / möjlig dubbelräkning":("Minska signalredundans","Mät inkrementell edge och identifiera signalfamiljer som räknar samma information flera gånger.","SIMPLIFICATION"),
"Decision Support är otillräckligt kalibrerat":("Fortsätt Decision Support-kalibrering","Samla mogna point-in-time-utfall för flera beslutslägen och horisonter innan modellen ges större betydelse.","CALIBRATION"),
"Partiell datakällhälsa":("Täta återkommande datagap","Identifiera vilka källor/fält som oftast är partiella och prioritera de gap som påverkar flest analyser.","DATA_RELIABILITY"),
}

def build_risk_roadmap(register:pd.DataFrame|None,max_items:int=5)->pd.DataFrame:
    cols=["Roadmap #","Riskprioritet","Severity","Utvecklingsspår","Nästa åtgärd","Kategori","Gate"]
    if register is None or register.empty:return pd.DataFrame(columns=cols)
    rows=[]
    for _,r in register.head(max_items).iterrows():
        risk=str(r.get("Risk") or "")
        if risk.startswith("Inga stora modellrisker"):
            continue
        title,action,cat=ACTION_MAP.get(risk,("Utred modellrisk",str(r.get("Recommended action") or ""),"REVIEW"))
        rows.append({
            "Riskprioritet":int(r.get("Prioritet") or len(rows)+1),
            "Severity":str(r.get("Severity") or ""),
            "Utvecklingsspår":title,
            "Nästa åtgärd":action,
            "Kategori":cat,
            "Gate":"Manuell granskning före produktionsändring",
        })
    out=pd.DataFrame(rows)
    if out.empty:return pd.DataFrame(columns=cols)
    out.insert(0,"Roadmap #",range(1,len(out)+1))
    return out[cols]

def roadmap_focus(roadmap:pd.DataFrame|None)->dict[str,Any]:
    if roadmap is None or roadmap.empty:
        return {"status":"Ingen riskstyrd utvecklingsåtgärd krävs just nu","next":"","reason":"Fortsätt samla prospektivt facit och bevaka Model Health."}
    r=roadmap.iloc[0]
    return {"status":"Nästa riskstyrda prioritet","next":str(r["Utvecklingsspår"]),
            "reason":f"{r['Severity']} · kommer från modellrisk #{int(r['Riskprioritet'])}. {r['Nästa åtgärd']}"}
