from __future__ import annotations
"""Decision support matrix separating idea strength from analysis confidence."""

import math
from typing import Any
import numpy as np
import pandas as pd

from analysis_confidence import assess_analysis_confidence


def _num(v: Any) -> float:
    try:
        x=float(v)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def assess_confidence_adjusted_decision(row: pd.Series | dict[str,Any]) -> dict[str,Any]:
    conviction=_num(row.get("Deal Conviction Score"))
    confidence=_num(row.get("Analysis Confidence Score"))
    if not np.isfinite(confidence):
        confidence=assess_analysis_confidence(row)["Analysis Confidence Score"]

    idea_strong=np.isfinite(conviction) and conviction>=60
    idea_exceptional=np.isfinite(conviction) and conviction>=75
    data_strong=np.isfinite(confidence) and confidence>=70
    data_weak=not np.isfinite(confidence) or confidence<50

    entry=str(row.get("Ingångsläge nivå") or "").lower()
    company=str(row.get("Bolagsbedömning nivå") or "").lower()
    blockers=str(row.get("Analysis Confidence blockerare") or "")
    if not blockers:
        blockers=assess_analysis_confidence(row).get("Analysis Confidence blockerare","")

    if idea_strong and data_strong and entry!="red" and company!="red":
        quadrant="STARK IDÉ / STARK DATA"
        label="💎 Stark idé · stark data"
        action="Högst prioritet för vidare beslut"
        level=4
    elif idea_strong and (data_weak or blockers):
        quadrant="STARK IDÉ / SVAG DATA"
        label="🟡 Stark idé · svag data"
        action="Verifiera datagapen innan hög övertygelse"
        level=3
    elif not idea_strong and data_strong:
        quadrant="SVAGARE IDÉ / STARK DATA"
        label="🔵 Svagare idé · stark data"
        action="Analysen är trovärdig men caset är inte tillräckligt attraktivt"
        level=2
    else:
        quadrant="SVAG IDÉ / SVAG DATA"
        label="⚪ Avstå / låg prioritet"
        action="För lite edge och/eller för svagt analysunderlag"
        level=1

    # Hard caution: bad entry/company can never render as highest-priority.
    cautions=[]
    if entry=="red": cautions.append("köpläget är rött")
    if company=="red": cautions.append("bolagsbedömningen är röd")
    if blockers: cautions.append("analysblockerare finns")
    if level==4 and cautions:
        level=3
        quadrant="STARK IDÉ / KRÄVER FÖRSIKTIGHET"
        label="🟠 Stark idé · men beslutet kräver försiktighet"
        action="Vänta på bättre beslutsförutsättningar"

    why=(
        f"Deal Conviction {conviction:.0f}/100 · Analysis Confidence {confidence:.0f}/100. "
        f"{action}."
    ) if np.isfinite(conviction) and np.isfinite(confidence) else (
        "Beslutsmatrisen saknar komplett conviction/confidence-underlag."
    )
    if cautions:
        why+=" Varningar: "+"; ".join(cautions)+"."
    why+=" Analysis Confidence påverkar inte Borsify Score eller Deal Conviction."

    return {
        "Decision Support":label,
        "Decision Support quadrant":quadrant,
        "Decision Support nivå":level,
        "Decision Support action":action,
        "Decision Support förklaring":why,
        "Decision Support conviction":conviction,
        "Decision Support confidence":confidence,
    }


def add_confidence_adjusted_decision(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df,pd.DataFrame) else pd.DataFrame()
    out=df.copy()

    # Ensure Analysis Confidence exists before the matrix is evaluated.
    if "Analysis Confidence Score" not in out.columns:
        conf=pd.DataFrame([assess_analysis_confidence(r) for _,r in out.iterrows()],index=out.index)
        overlap=[c for c in conf.columns if c in out.columns]
        if overlap:
            out=out.drop(columns=overlap)
        out=out.join(conf)

    extra=pd.DataFrame([assess_confidence_adjusted_decision(r) for _,r in out.iterrows()],index=out.index)
    overlap=[c for c in extra.columns if c in out.columns]
    if overlap:
        out=out.drop(columns=overlap)
    return out.join(extra)
