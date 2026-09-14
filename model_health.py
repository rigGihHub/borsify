from __future__ import annotations
"""Borsify model-health diagnostics.

This evaluates the state of Borsify's evidence base, not stocks. It is deliberately
conservative and advisory: no score, signal, gate or production weight is mutated.
"""

from typing import Any
import math
import numpy as np
import pandas as pd


def assess_model_health(
    evidence: pd.DataFrame | None,
    governance: pd.DataFrame | None,
    redundancy: pd.DataFrame | None,
    decision_quality: pd.DataFrame | None,
) -> dict[str, Any]:
    evidence = evidence.copy() if isinstance(evidence,pd.DataFrame) else pd.DataFrame()
    governance = governance.copy() if isinstance(governance,pd.DataFrame) else pd.DataFrame()
    redundancy = redundancy.copy() if isinstance(redundancy,pd.DataFrame) else pd.DataFrame()
    decision_quality = decision_quality.copy() if isinstance(decision_quality,pd.DataFrame) else pd.DataFrame()

    total_signals=int(len(evidence))
    matured=0
    promising=0
    warning=0
    unclear=0
    if not evidence.empty:
        status=evidence.get("Status",pd.Series(index=evidence.index,dtype=object)).astype(str)
        promising=int(status.str.startswith("Lovande").sum())
        warning=int(status.str.startswith("Varningssignal").sum())
        matured=int((~status.eq("Bygger facit")).sum())
        unclear=max(total_signals-promising-warning-int(status.eq("Ingen tydlig edge").sum())-int(status.eq("Bygger facit").sum()),0)

    promote=merge_review=retire=observe=0
    if not governance.empty and "Action" in governance.columns:
        acts=governance["Action"].astype(str)
        promote=int(acts.eq("PROMOTE CANDIDATE").sum())
        merge_review=int(acts.eq("MERGE REVIEW").sum())
        retire=int(acts.eq("RETIRE/DOWNWEIGHT CANDIDATE").sum())
        observe=int(acts.eq("KEEP OBSERVING").sum())

    redundant_pairs=int(len(redundancy)) if not redundancy.empty else 0

    dq_mature=0
    if not decision_quality.empty and "Status" in decision_quality.columns:
        dq_mature=int(decision_quality["Status"].astype(str).eq("Moget nog för jämförelse").sum())

    # Score rewards maturity and positive evidence, but penalises negative/redundant signals.
    maturity_ratio=(matured/total_signals) if total_signals else 0.0
    positive_ratio=(promising/matured) if matured else 0.0

    score=20.0
    score += 35.0*maturity_ratio
    score += 20.0*positive_ratio
    score += min(promote,3)*4.0
    score += min(dq_mature,3)*3.0
    score -= min(warning,5)*6.0
    score -= min(retire,5)*8.0
    score -= min(merge_review+redundant_pairs,6)*3.0
    score=float(np.clip(score,0,100))

    if score>=80 and matured>=8 and warning==0 and retire==0:
        label="💎 Hög modellhälsa"
        level=4
    elif score>=60:
        label="🟢 God modellhälsa"
        level=3
    elif score>=40:
        label="🟡 Modellhälsan är blandad"
        level=2
    else:
        label="🔴 Svag/omogen modellhälsa"
        level=1

    risks=[]
    if total_signals and matured<max(3,total_signals//3):
        risks.append("stor del av signalerna saknar moget prospektivt facit")
    if warning:
        risks.append(f"{warning} signal(er) underpresterar kontroll")
    if retire:
        risks.append(f"{retire} signal(er) är retire/downweight-kandidat(er)")
    if merge_review or redundant_pairs:
        risks.append("signalredundans behöver granskas")
    if dq_mature<2:
        risks.append("beslutslägena har begränsad mogen kalibrering")

    strengths=[]
    if promising:
        strengths.append(f"{promising} signal(er) visar preliminär edge")
    if promote:
        strengths.append(f"{promote} promotion-kandidat(er)")
    if maturity_ratio>=.5:
        strengths.append("minst hälften av signalerna har moget facit")
    if dq_mature>=2:
        strengths.append("flera beslutslägen har mogna utfall")

    return {
        "Model Health":label,
        "Model Health Score":score,
        "Model Health nivå":level,
        "Model Health signaler":total_signals,
        "Model Health mogna":matured,
        "Model Health lovande":promising,
        "Model Health varningar":warning,
        "Model Health promote":promote,
        "Model Health merge":merge_review,
        "Model Health retire":retire,
        "Model Health decision mature":dq_mature,
        "Model Health styrkor":"; ".join(strengths),
        "Model Health risker":"; ".join(risks),
        "Model Health förklaring":(
            f"{matured}/{total_signals} signaler har moget prospektivt facit. "
            f"{promising} är preliminärt lovande, {warning} varningssignal(er), "
            f"{merge_review} merge review och {retire} retire/downweight-kandidat(er). "
            "Detta mäter Borsifys evidensmognad och ändrar aldrig produktionen automatiskt."
        ),
    }
