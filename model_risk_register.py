from __future__ import annotations
from typing import Any
import pandas as pd

SEVERITY_ORDER={"CRITICAL":0,"HIGH":1,"MEDIUM":2,"LOW":3}

def build_model_risk_register(model_health:dict[str,Any]|None,evidence:pd.DataFrame|None,
                              governance:pd.DataFrame|None,redundancy:pd.DataFrame|None,
                              decision_quality:pd.DataFrame|None,source_summary:dict[str,Any]|None=None)->pd.DataFrame:
    cols=["Prioritet","Severity","Risk","Evidence","Impact","Recommended action","Auto action"]
    mh=model_health or {}
    redundancy=redundancy if isinstance(redundancy,pd.DataFrame) else pd.DataFrame()
    source_summary=source_summary or {}
    rows=[]
    total=int(mh.get("Model Health signaler",0) or 0); mature=int(mh.get("Model Health mogna",0) or 0)
    warnings=int(mh.get("Model Health varningar",0) or 0); retire=int(mh.get("Model Health retire",0) or 0)
    merge=int(mh.get("Model Health merge",0) or 0); dq=int(mh.get("Model Health decision mature",0) or 0)

    def add(sev,risk,evidence,impact,action):
        rows.append({"Severity":sev,"Risk":risk,"Evidence":evidence,"Impact":impact,"Recommended action":action,"Auto action":"Ingen"})

    if total and mature < max(3,total//3):
        add("HIGH","Otillräcklig prospektiv PIT-historik",f"{mature}/{total} signaler har moget facit",
            "Risk att slutsatser bygger mer på hypoteser än verifierade utfall.",
            "Prioritera mognad och datainsamling före nya signaler.")
    if warnings:
        add("HIGH","Signaler med negativ observerad edge",f"{warnings} signal(er) underpresterar kontroll",
            "Kan dra rankingen i fel riktning om signalerna fortfarande påverkar produktionen.",
            "Kör separat kill/downweight-granskning med kohort-, regim- och datakvalitetskontroll.")
    if retire:
        add("CRITICAL","Retire/downweight-kandidater finns",f"{retire} signal(er) har retire/downweight-status",
            "Modellen kan bära signaler som prospektivt ser skadliga ut.",
            "Manuell avvecklingsgranskning före ytterligare modellkomplexitet.")
    red_pairs=len(redundancy) if not redundancy.empty else 0
    if merge or red_pairs:
        add("MEDIUM","Signalredundans / möjlig dubbelräkning",f"{merge} merge review · {red_pairs} högt korrelerade par",
            "Samma information kan räknas flera gånger och skapa falsk säkerhet.",
            "Mät inkrementellt värde och slå ihop signaler utan unik edge.")
    if dq<2:
        add("MEDIUM","Decision Support är otillräckligt kalibrerat",f"{dq} beslutsläge(n) har moget jämförelseunderlag",
            "Skillnaden mellan stark och svag data är ännu inte väl verifierad.",
            "Fortsätt frysa beslutslägen och utvärdera dem över flera horisonter.")
    src_error=int(source_summary.get("error",0) or 0); src_circuit=int(source_summary.get("circuit",0) or 0)
    src_warning=int(source_summary.get("warning",0) or 0)
    if src_error or src_circuit:
        add("CRITICAL","Aktiva datakällfel påverkar analyskedjan",f"{src_error} fel · {src_circuit} öppna circuit breakers",
            "Färsk analys kan vara ofullständig eller blockerad.",
            "Återställ källor och verifiera berörda analyser innan högt förtroende.")
    elif src_warning:
        add("MEDIUM","Partiell datakällhälsa",f"{src_warning} källa/källor är partiella",
            "Vissa analysfamiljer kan ha lägre täckning än önskat.",
            "Följ upp datagap och source-health innan de blir permanenta.")
    if not rows:
        add("LOW","Inga stora modellrisker identifierade av nuvarande register","Inga tröskelöverträdelser",
            "Det betyder inte att modellen är riskfri.","Fortsätt prospektiv validering och periodisk riskgranskning.")
    out=pd.DataFrame(rows)
    out["_sev"]=out["Severity"].map(SEVERITY_ORDER).fillna(9)
    out=out.sort_values(["_sev","Risk"],kind="stable").drop(columns="_sev").reset_index(drop=True)
    out.insert(0,"Prioritet",range(1,len(out)+1))
    return out[cols]

def summarize_model_risks(register:pd.DataFrame|None)->dict[str,Any]:
    if register is None or register.empty:
        return {"status":"⚪ Inget riskregister ännu","critical":0,"high":0,"medium":0,"text":"Ingen modellriskdata finns."}
    sev=register["Severity"].astype(str)
    c=int(sev.eq("CRITICAL").sum()); h=int(sev.eq("HIGH").sum()); m=int(sev.eq("MEDIUM").sum())
    status="🔴 Kritiska modellrisker kräver granskning" if c else "🟠 Höga modellrisker finns" if h else "🟡 Modellrisker bör bevakas" if m else "🟢 Inga stora riskflaggor just nu"
    return {"status":status,"critical":c,"high":h,"medium":m,
            "text":f"{c} kritiska · {h} höga · {m} medel. Riskregistret är rådgivande och ändrar aldrig modellen automatiskt."}
