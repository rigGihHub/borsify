from __future__ import annotations

"""Value Chain Read-through Engine.

Conservative cross-company discovery using explicit industry-role relationships rather
than broad same-sector matching. The map is a transparent heuristic taxonomy, not a
claim that two named companies are actual customers/suppliers. A target still needs
its own fundamental support and must have no fresh negative evidence or obvious run-up.
No score is created.
"""
from typing import Any
import math
import pandas as pd


def _text(v: Any) -> str:
    return str(v or "").strip()


def _num(v: Any) -> float:
    try:
        x=float(v); return x if math.isfinite(x) else float('nan')
    except Exception: return float('nan')


def _bool(v: Any) -> bool:
    try:
        if pd.isna(v): return False
    except Exception: pass
    return bool(v)

# Role classification uses Yahoo industry/sector text. Rules are intentionally broad,
# auditable and direction-aware. They model economic adjacency, never named contracts.
ROLE_RULES = [
    ("semiconductors", ("semiconductor", "chip")),
    ("electronics_components", ("electronic components", "electrical equipment", "electronic equipment")),
    ("industrial_machinery", ("specialty industrial machinery", "farm & heavy construction machinery", "industrial distribution", "tools & accessories", "machinery")),
    ("autos", ("auto manufacturers", "automobiles", "auto parts", "recreational vehicles")),
    ("construction_inputs", ("building materials", "steel", "aluminum", "copper", "specialty chemicals", "lumber")),
    ("construction", ("engineering & construction", "residential construction", "building products & equipment", "infrastructure operations")),
    ("energy_inputs", ("oil & gas", "uranium", "coal", "solar", "utilities—renewable")),
    ("transport", ("trucking", "railroads", "marine shipping", "integrated freight & logistics", "airlines")),
    ("retail", ("specialty retail", "department stores", "grocery stores", "internet retail")),
    ("consumer_brands", ("packaged foods", "beverages", "apparel manufacturing", "household & personal products")),
]

# source_role -> target_roles with plain-language economic rationale.
ADJACENCY = {
    "semiconductors": {"electronics_components": "chip/komponentkedja", "industrial_machinery": "automation och elektronik i industrin", "autos": "fordonselektronik"},
    "electronics_components": {"industrial_machinery": "komponenter till industrisystem", "autos": "elektronik/komponenter till fordon"},
    "construction_inputs": {"construction": "insatsvaror till bygg/infrastruktur"},
    "energy_inputs": {"industrial_machinery": "energiinvesteringar driver utrustningsbehov", "transport": "energi- och bränslekostnad påverkar transport"},
    "industrial_machinery": {"construction": "maskiner/utrustning till bygg och infrastruktur"},
    "consumer_brands": {"retail": "varumärken och produkter säljs genom återförsäljare"},
    "transport": {"retail": "logistik är en del av varuflödet till handel"},
}


def classify_value_chain_role(row: pd.Series) -> str:
    hay = f"{_text(row.get('Bransch'))} {_text(row.get('Sektor'))}".casefold()
    for role, terms in ROLE_RULES:
        if any(t.casefold() in hay for t in terms):
            return role
    return ""


def _source_strength(row: pd.Series) -> tuple[int, str]:
    report = _bool(row.get("Report Delta kandidat")); rp=_num(row.get("Report Delta positiva")); rn=_num(row.get("Report Delta negativa"))
    mgmt = _bool(row.get("Ledningssignal kandidat")); warn=_bool(row.get("Ledningssignal varning"))
    if report and rp >= 4 and (not math.isfinite(rn) or rn <= 0) and mgmt and not warn:
        return 3, "rapportförbättring + positiv ledningssignal"
    if report and rp >= 4 and (not math.isfinite(rn) or rn <= 0): return 2, "bred positiv rapportförändring"
    if mgmt and not warn: return 1, "konkreta positiva ledningssignaler"
    return 0, ""


def add_value_chain_readthrough(df: pd.DataFrame) -> pd.DataFrame:
    if df is None: return pd.DataFrame()
    out=df.copy()
    defaults={
        "Värdekedja roll":"", "Värdekedja status":"Ingen verifierbar värdekedjeläsning",
        "Värdekedja kandidat":False, "Värdekedja stark":False, "Värdekedja källor antal":0,
        "Värdekedja källbolag":"", "Värdekedja relation":"", "Värdekedja förklaring":""
    }
    for c,v in defaults.items(): out[c]=v
    if out.empty: return out
    roles={idx:classify_value_chain_role(row) for idx,row in out.iterrows()}
    for idx,role in roles.items(): out.at[idx,"Värdekedja roll"]=role
    sources=[]
    for idx,row in out.iterrows():
        strength,why=_source_strength(row); role=roles[idx]
        if strength>0 and role: sources.append((idx,role,strength,why))
    for idx,row in out.iterrows():
        target_role=roles[idx]
        if not target_role: continue
        matches=[]
        for sidx,srole,strength,why in sources:
            if sidx==idx: continue
            relation=ADJACENCY.get(srole,{}).get(target_role)
            if relation: matches.append((sidx,srole,strength,why,relation))
        if not matches: continue
        own_fund=_num(row.get("Fundamental upptäckt antal"))
        own_neg=_bool(row.get("Ledningssignal varning")) or _num(row.get("Report Delta negativa"))>=2 or "marknaden säger emot" in _text(row.get("Report Delta status")).casefold()
        m1=_num(row.get("1 mån")); ran=math.isfinite(m1) and m1>0.12
        matches=sorted(matches,key=lambda x:(-x[2],_text(out.at[x[0],"Ticker"])))
        names=[_text(out.at[m[0],"Namn"]) or _text(out.at[m[0],"Ticker"]) for m in matches]
        rels=list(dict.fromkeys(m[4] for m in matches))
        candidate=bool(own_fund>=1 and not own_neg and not ran)
        strong=bool(candidate and (len({m[0] for m in matches})>=2 or max(m[2] for m in matches)>=3))
        if own_neg: status="Värdekedja positiv – eget motbevis väger tyngre"; candidate=strong=False
        elif ran: status="Värdekedja positiv – aktien har redan rört sig tydligt"; candidate=strong=False
        elif own_fund<1: status="Värdekedja positiv – saknar eget fundamentalt stöd"; candidate=strong=False
        elif strong: status="Stark värdekedjeläsning"
        else: status="Möjlig värdekedjeläsning"
        out.at[idx,"Värdekedja status"]=status; out.at[idx,"Värdekedja kandidat"]=candidate; out.at[idx,"Värdekedja stark"]=strong
        out.at[idx,"Värdekedja källor antal"]=len({m[0] for m in matches}); out.at[idx,"Värdekedja källbolag"]=', '.join(dict.fromkeys(names[:3]))
        out.at[idx,"Värdekedja relation"]='; '.join(rels[:3])
        out.at[idx,"Värdekedja förklaring"]=(f"Positiv förändring observeras uppströms/närliggande via {', '.join(dict.fromkeys(names[:3]))}. "
            f"Kopplingen bygger på transparent branschroll: {'; '.join(rels[:3])}. "
            + ("Bolaget har eget fundamentalt discovery-stöd. " if own_fund>=1 else "Bolaget saknar eget fundamentalt discovery-stöd. ")
            + "Detta bevisar inte ett faktiskt kund-/leverantörsförhållande mellan de namngivna bolagen.")
    return out


def select_value_chain_candidates(df: pd.DataFrame, quota: int=1) -> list[tuple[Any,str]]:
    if df is None or df.empty or quota<=0 or "Värdekedja kandidat" not in df.columns: return []
    w=df[df["Värdekedja kandidat"].fillna(False).astype(bool)].copy()
    if w.empty: return []
    w["__strong"]=w.get("Värdekedja stark",False).fillna(False).astype(int)
    w["__sources"]=pd.to_numeric(w.get("Värdekedja källor antal"),errors="coerce").fillna(0)
    w["__fund"]=pd.to_numeric(w.get("Fundamental upptäckt antal"),errors="coerce").fillna(0)
    w["__m1"]=pd.to_numeric(w.get("1 mån"),errors="coerce").fillna(999)
    w["__ticker"]=w.get("Ticker",pd.Series("",index=w.index)).astype(str)
    w=w.sort_values(["__strong","__sources","__fund","__m1","__ticker"],ascending=[False,False,False,True,True])
    return [(idx,"Värdekedja") for idx in w.index[:quota]]
