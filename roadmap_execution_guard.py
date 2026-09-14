from __future__ import annotations
"""Turn Risk-to-Roadmap into executable-but-safe engineering guidance."""
from typing import Any
import pandas as pd

GATES={
"MODEL_VALIDATION":("Valideringsgrind","Kräv moget PIT-facit, flera horisonter/regimer och manuell review före viktändring."),
"DATA_RELIABILITY":("Datagrind","Kräv återställd source health och verifierad komplett analyskedja."),
"EVIDENCE":("Evidensgrind","Kräv fler frysta prospektiva snapshots; förbjud historisk backfill av saknade signaler."),
"SIMPLIFICATION":("Redundansgrind","Kräv inkrementell edge efter matchning innan signaler slås ihop eller tas bort."),
"CALIBRATION":("Kalibreringsgrind","Kräv mogna grupper på flera horisonter innan Decision Support får större produktionsbetydelse."),
"REVIEW":("Manuell grind","Kräv dokumenterad manuell granskning."),
}

def build_execution_plan(roadmap:pd.DataFrame|None)->pd.DataFrame:
    cols=["Steg","Utvecklingsspår","Kategori","Definition of done","Produktionsändring","Status"]
    if roadmap is None or roadmap.empty:return pd.DataFrame(columns=cols)
    rows=[]
    for _,r in roadmap.iterrows():
        cat=str(r.get("Kategori") or "REVIEW")
        gate_name,done=GATES.get(cat,GATES["REVIEW"])
        rows.append({
            "Utvecklingsspår":str(r.get("Utvecklingsspår") or ""),
            "Kategori":cat,
            "Definition of done":f"{gate_name}: {done}",
            "Produktionsändring":"BLOCKERAD tills grinden är uppfylld",
            "Status":"PLANERAD",
        })
    out=pd.DataFrame(rows)
    out.insert(0,"Steg",range(1,len(out)+1))
    return out[cols]

def next_safe_work_item(plan:pd.DataFrame|None)->dict[str,Any]:
    if plan is None or plan.empty:
        return {"work":"","status":"Ingen blockerande riskåtgärd","done":"Fortsätt prospektiv observation."}
    r=plan.iloc[0]
    return {"work":str(r["Utvecklingsspår"]),"status":"Nästa säkra arbetsobjekt","done":str(r["Definition of done"])}

def production_change_allowed(plan:pd.DataFrame|None)->bool:
    # This module deliberately cannot approve model changes. Approval belongs to
    # explicit governance after evidence review.
    return False
