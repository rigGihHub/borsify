from __future__ import annotations
import math
from typing import Any
import numpy as np
import pandas as pd

def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan

def _text(v: Any) -> str:
    if isinstance(v,(list,tuple)):
        return "; ".join(str(x) for x in v if str(x).strip())
    return str(v or "").strip()

def _profile(sector: str, industry: str) -> tuple[str,list[str]]:
    s=(sector+" "+industry).lower()
    if any(x in s for x in ["bank","financial","insurance","credit"]):
        return "Finans", ["CET1/kapitalrelation","kreditförluster","räntenetto/marginal","inlånings-/finansieringsmix"]
    if any(x in s for x in ["software","saas","internet","technology","it services"]):
        return "Mjukvara/tech", ["ARR/återkommande intäkter","NRR/churn","CAC/payback","bruttomarginal/FCF-konvertering"]
    if any(x in s for x in ["retail","consumer cyclical","apparel","restaurant"]):
        return "Retail/konsument", ["like-for-like","lagerutveckling","bruttomarginal","butiks-/kanalekonomi"]
    if any(x in s for x in ["industrial","machinery","engineering","aerospace","construction"]):
        return "Industri", ["orderingång/orderbok","pris/mix","kapacitetsutnyttjande","marginal/FCF genom cykeln"]
    if any(x in s for x in ["health","biotech","pharma","medical"]):
        return "Hälsovård", ["pipeline/milstolpar","volym/adoption","bruttomarginal","regulatoriska/kliniska risker"]
    if any(x in s for x in ["energy","oil","gas","mining","materials"]):
        return "Råvara/energi", ["volym/produktion","realiserat pris","enhetskostnad","capex/FCF vid olika råvarupriser"]
    return "Generell verksamhet", ["organisk tillväxt","marginalutveckling","kassaflödeskonvertering","kapitalallokering"]

def assess_business_management_intelligence(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    r=row
    sector=_text(r.get("Sektor")); industry=_text(r.get("Bransch"))
    profile,kpis=_profile(sector,industry)

    observed=[]; missing=[]
    # Generic proxies that are actually available today.
    if np.isfinite(_num(r.get("Omsättningstillväxt"))): observed.append("omsättningstillväxt")
    if np.isfinite(_num(r.get("Vinstmarginal"))): observed.append("vinstmarginal")
    if np.isfinite(_num(r.get("FCF-yield"))) or np.isfinite(_num(r.get("FCF yield"))): observed.append("FCF-yield")
    if np.isfinite(_num(r.get("ROE"))): observed.append("ROE")
    if np.isfinite(_num(r.get("Skuld/eget kapital"))): observed.append("skuldsättning")

    # Sector-specific KPI fields are intentionally not fabricated. If none of the known
    # structured fields exist, surface the gap explicitly.
    aliases={
        "ARR/återkommande intäkter":["ARR","Recurring revenue","Återkommande intäkter","NRR"],
        "NRR/churn":["NRR","Churn"],
        "CAC/payback":["CAC","CAC payback"],
        "like-for-like":["Like-for-like","LFL"],
        "lagerutveckling":["Lagerförändring","Inventory growth"],
        "orderingång/orderbok":["Orderingång","Orderbok","Book-to-bill"],
        "CET1/kapitalrelation":["CET1","Kapitalrelation"],
        "kreditförluster":["Kreditförlustnivå","Credit loss ratio"],
        "räntenetto/marginal":["Räntenetto","NIM"],
        "pipeline/milstolpar":["Pipeline status","Clinical milestones"],
        "volym/produktion":["Produktionstillväxt","Production growth"],
        "enhetskostnad":["Unit cost","Enhetskostnad"],
    }
    structured_specific=_text(r.get("KPI-specifika observerade"))
    structured_missing=_text(r.get("KPI-specifika saknas"))
    specific_seen=len([x for x in structured_specific.split(";") if x.strip()])
    if structured_specific:
        observed.extend([x.strip() for x in structured_specific.split(";") if x.strip()])
    if structured_missing:
        missing.extend([x.strip() for x in structured_missing.split(";") if x.strip()])
    for k in kpis:
        al=aliases.get(k,[])
        if any(_text(r.get(a)) not in {"","nan","None"} for a in al):
            specific_seen += 1
        elif al:
            missing.append(k)

    guidance=_text(r.get("Report Delta guidance"))
    strengths=_text(r.get("Report Delta styrkor"))
    warnings=_text(r.get("Report Delta varningar"))
    report_pos=_num(r.get("Report Delta positiva")); report_neg=_num(r.get("Report Delta negativa"))
    buyback=_num(r.get("Kapitalallokering återköpsyield"))
    issuance=_num(r.get("Kapitalallokering emissionsyield"))
    debt_trend=_num(r.get("Kapitalallokering skuldtrend"))

    mgmt_support=[]; mgmt_warn=[]
    gl=guidance.lower()
    if guidance and "ingen explicit guidningsförändring" not in gl:
        if any(x in gl for x in ["höj","raised","raise","upgraded"]): mgmt_support.append("guidance har höjts")
        if any(x in gl for x in ["sänk","cut","lowered","profit warning"]): mgmt_warn.append("guidance har sänkts")
    if np.isfinite(report_pos) and np.isfinite(report_neg):
        if report_pos>=3 and report_neg<=1: mgmt_support.append("senaste rapporten visar bred positiv leverans")
        elif report_neg>=2 and report_neg>report_pos: mgmt_warn.append("senaste rapporten visar bred negativ leverans")
    if np.isfinite(buyback) and buyback>=.01: mgmt_support.append("observerade nettoåterköp")
    if np.isfinite(issuance) and issuance>=.03: mgmt_warn.append("betydande aktieemission")
    if np.isfinite(debt_trend):
        if debt_trend<=-.10: mgmt_support.append("skuldtrenden förbättras")
        elif debt_trend>=.20: mgmt_warn.append("skuldtrenden försämras")

    # This is execution evidence, not a CEO-quality score. Historical promise-vs-delivery
    # is not claimed until repeated guidance snapshots exist.
    evidence=len(mgmt_support)+len(mgmt_warn)
    if evidence<2:
        mgmt_label="— För lite historik för ledningsbedömning"; mgmt_level=0
    elif len(mgmt_warn)>=2 and len(mgmt_warn)>len(mgmt_support):
        mgmt_label="⚠️ Ledningens senaste execution ger varningar"; mgmt_level=-1
    elif len(mgmt_support)>=3 and len(mgmt_warn)==0:
        mgmt_label="🟢 Stark observerad execution"; mgmt_level=2
    else:
        mgmt_label="🟡 Blandad/partiell execution-evidens"; mgmt_level=1

    if specific_seen>=2:
        coverage_label="🟢 Bransch-KPI-underlag finns"
    elif specific_seen==1:
        coverage_label="🟡 Delvis bransch-KPI-underlag"
    else:
        coverage_label="⚠️ Branschspecifika KPI:er saknas i strukturerad data"

    return {
        "Business profile": profile,
        "Business key KPIs": "; ".join(kpis),
        "Business observed generic KPIs": "; ".join(observed),
        "Business KPI gaps": "; ".join(missing if missing else ([k for k in kpis] if specific_seen==0 else [])),
        "Business KPI coverage": coverage_label,
        "Management execution": mgmt_label,
        "Management execution nivå": mgmt_level,
        "Management execution stöd": "; ".join(mgmt_support),
        "Management execution varningar": "; ".join(mgmt_warn),
        "Management execution evidens": evidence,
        "Management execution förklaring": (
            ("; ".join(mgmt_support) if mgmt_support else "ingen stark positiv execution-evidens")
            + (". Motargument: " + "; ".join(mgmt_warn) if mgmt_warn else "")
            + ". Detta mäter observerad execution i tillgänglig data, inte VD-kvalitet. Historisk löftesprecision kräver fler frysta guidance-snapshots."
        ),
    }

def add_business_management_intelligence(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()
    extra=pd.DataFrame([assess_business_management_intelligence(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap: out=out.drop(columns=overlap)
    return out.join(extra)
