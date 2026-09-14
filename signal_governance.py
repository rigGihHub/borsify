from __future__ import annotations

from typing import Any, Iterable
import math
import numpy as np

import pandas as pd

from literature_signal_validation import SIGNALS, validate_literature_signals

# Governance is deliberately conservative. A single horizon can never promote,
# de-emphasise or retire a signal. These labels are review recommendations only.
MIN_REVIEW_HORIZONS = 2
MIN_RETIRE_HORIZONS = 3
MIN_REVIEW_CASES = 24
MIN_RETIRE_CASES = 48

ACTION_KEEP = "Behåll – stöd i historiken"
ACTION_MIXED = "Behåll under bevakning"
ACTION_DEEMPHASISE = "Granska för nedtoning"
ACTION_RETIRE = "Kandidat för avveckling"
ACTION_WAIT = "Vänta på mer data"


def _clean_horizons(values: Iterable[Any]) -> list[str]:
    preferred = ["1m", "3m", "6m", "1y", "2y"]
    unique = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in unique:
            unique.append(text)
    order = {name: i for i, name in enumerate(preferred)}
    return sorted(unique, key=lambda x: (order.get(x, 99), x))


def governance_decision(signal_rows: pd.DataFrame) -> dict[str, Any]:
    """Turn horizon-level validation into a conservative manual-review action.

    Horizon results are robustness checks, not independent observations. Therefore we
    use the largest independent sample at any one horizon rather than summing case
    counts across horizons. No production weight, gate or threshold is changed here.
    """
    if signal_rows is None or signal_rows.empty:
        return {
            "Åtgärd": ACTION_WAIT,
            "Utvärderade horisonter": 0,
            "Lovande horisonter": 0,
            "Ifrågasatta horisonter": 0,
            "Oklara horisonter": 0,
            "Största oberoende sample": 0,
            "Skäl": "Ingen mogen point-in-time-historik ännu.",
        }

    work = signal_rows.copy()
    status = work.get("Status", pd.Series(index=work.index, dtype=object)).astype(str)
    evaluated = work[status.isin({"Lovande", "Ifrågasatt", "Oklart"})]
    n_eval = int(len(evaluated))
    n_promising = int((status == "Lovande").sum())
    n_questioned = int((status == "Ifrågasatt").sum())
    n_unclear = int((status == "Oklart").sum())
    max_cases = int(pd.to_numeric(work.get("Oberoende case", 0), errors="coerce").fillna(0).max()) if len(work) else 0

    action = ACTION_WAIT
    reason = "Historiken är ännu för tunn eller för ensidig för en modellåtgärd."

    # Retirement is intentionally the hardest label to reach.
    if (
        n_eval >= MIN_RETIRE_HORIZONS
        and n_questioned == n_eval
        and max_cases >= MIN_RETIRE_CASES
    ):
        action = ACTION_RETIRE
        reason = (
            f"Signalen är ifrågasatt på alla {n_eval} utvärderade horisonter och största "
            f"oberoende samplet är {max_cases} case. Granska signalen för möjlig avveckling."
        )
    elif (
        n_eval >= MIN_REVIEW_HORIZONS
        and n_questioned >= MIN_REVIEW_HORIZONS
        and n_promising == 0
        and max_cases >= MIN_REVIEW_CASES
    ):
        action = ACTION_DEEMPHASISE
        reason = (
            f"Signalen är ifrågasatt på {n_questioned} av {n_eval} utvärderade horisonter "
            "utan någon lovande horisont. Granska om den ska få mindre betydelse."
        )
    elif n_promising > 0 and n_questioned > 0:
        action = ACTION_MIXED
        reason = (
            f"Evidensen är blandad: {n_promising} lovande och {n_questioned} ifrågasatt(a) "
            "horisont(er). Behåll signalen oförändrad tills mönstret blir tydligare."
        )
    elif (
        n_eval >= MIN_REVIEW_HORIZONS
        and n_promising >= MIN_REVIEW_HORIZONS
        and n_questioned == 0
        and max_cases >= MIN_REVIEW_CASES
    ):
        action = ACTION_KEEP
        reason = (
            f"Signalen är lovande på {n_promising} av {n_eval} utvärderade horisonter och "
            "ingen horisont är ifrågasatt. Det stödjer att behålla signalen, inte att automatiskt öka vikten."
        )

    return {
        "Åtgärd": action,
        "Utvärderade horisonter": n_eval,
        "Lovande horisonter": n_promising,
        "Ifrågasatta horisonter": n_questioned,
        "Oklara horisonter": n_unclear,
        "Största oberoende sample": max_cases,
        "Skäl": reason,
    }


def build_signal_governance(
    recommendations: pd.DataFrame,
    outcomes: pd.DataFrame,
    horizons: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build a cross-horizon governance table for the literature-inspired signals.

    Only frozen point-in-time observations are used via validate_literature_signals().
    The result is advisory: it never mutates model parameters or production state.
    """
    if horizons is None:
        if outcomes is None or outcomes.empty or "horizon" not in outcomes.columns:
            horizon_list: list[str] = []
        else:
            horizon_list = _clean_horizons(outcomes["horizon"].dropna().tolist())
    else:
        horizon_list = _clean_horizons(horizons)

    by_horizon: dict[str, pd.DataFrame] = {}
    for horizon in horizon_list:
        table = validate_literature_signals(recommendations, outcomes, horizon)
        if not table.empty:
            by_horizon[horizon] = table

    rows: list[dict[str, Any]] = []
    for spec in SIGNALS:
        pieces = []
        status_parts = []
        for horizon, table in by_horizon.items():
            match = table[table["Signal"].eq(spec.name)]
            if match.empty:
                continue
            part = match.iloc[0].to_dict()
            part["Horisont"] = horizon
            pieces.append(part)
            status_parts.append(f"{horizon}: {part.get('Status', '—')}")

        detail = pd.DataFrame(pieces)
        decision = governance_decision(detail)
        rows.append({
            "Signal": spec.name,
            "Modell": "Lång" if spec.model == "long" else "Kort",
            **decision,
            "Horisonter": " · ".join(status_parts) if status_parts else "Ingen mogen historik",
        })

    result = pd.DataFrame(rows)
    priority = {
        ACTION_RETIRE: 0,
        ACTION_DEEMPHASISE: 1,
        ACTION_MIXED: 2,
        ACTION_KEEP: 3,
        ACTION_WAIT: 4,
    }
    result["_order"] = result["Åtgärd"].map(priority).fillna(9)
    return result.sort_values(["_order", "Signal"], kind="stable").drop(columns="_order").reset_index(drop=True)


def signal_governance_summary(table: pd.DataFrame) -> dict[str, str]:
    if table is None or table.empty:
        return {"status": ACTION_WAIT, "text": "Det finns ännu ingen signalhistorik att förvalta."}

    retire = table[table["Åtgärd"].eq(ACTION_RETIRE)]
    down = table[table["Åtgärd"].eq(ACTION_DEEMPHASISE)]
    mixed = table[table["Åtgärd"].eq(ACTION_MIXED)]
    keep = table[table["Åtgärd"].eq(ACTION_KEEP)]

    if not retire.empty:
        names = ", ".join(retire["Signal"].head(2).astype(str))
        return {
            "status": ACTION_RETIRE,
            "text": f"{names} har tillräckligt konsekvent negativ historik för manuell avvecklingsgranskning. Ingenting tas bort automatiskt.",
        }
    if not down.empty:
        names = ", ".join(down["Signal"].head(2).astype(str))
        return {
            "status": ACTION_DEEMPHASISE,
            "text": f"{names} bör granskas för mindre betydelse. Borsify ändrar inga vikter automatiskt.",
        }
    if not mixed.empty:
        return {
            "status": ACTION_MIXED,
            "text": "Minst en signal har olika resultat på olika horisonter. Det talar för att behålla modellen oförändrad och samla mer historik.",
        }
    if not keep.empty:
        names = ", ".join(keep["Signal"].head(2).astype(str))
        return {
            "status": ACTION_KEEP,
            "text": f"{names} har stöd på flera horisonter. Det motiverar att behålla signalen, men inte att höja vikten automatiskt.",
        }
    return {
        "status": ACTION_WAIT,
        "text": "De nya signalerna är fortfarande för unga för promotion, nedtoning eller avveckling. Borsify väntar på fler mogna utfall.",
    }

# v4.11 Evidence Lab governance nominations
def nominate_signal_actions(evidence:pd.DataFrame|None, redundancy:pd.DataFrame|None,
                            min_cases:int=20, promote_edge:float=.03, retire_edge:float=-.03)->pd.DataFrame:
    cols=["Signal","Action","Evidence","Reason"]
    if evidence is None or evidence.empty:return pd.DataFrame(columns=cols)
    red={}
    if redundancy is not None and not redundancy.empty:
        for _,r in redundancy.iterrows():
            a,b=str(r["Signal A"]),str(r["Signal B"])
            c=float(r["Korrelation"])
            red.setdefault(a,[]).append((b,c)); red.setdefault(b,[]).append((a,c))
    rows=[]
    for _,r in evidence.iterrows():
        sig=str(r["Signal"]); n=int(r.get("Signal N",0)); ctl=int(r.get("Control N",0))
        try:edge=float(r.get("Median edge"))
        except Exception:edge=np.nan
        enough=n>=min_cases and ctl>=min_cases
        overlaps=sorted(red.get(sig,[]),key=lambda x:abs(x[1]),reverse=True)
        if enough and overlaps and abs(overlaps[0][1])>=.80:
            action="MERGE REVIEW"
            reason=f"Hög överlappning med {overlaps[0][0]} ({overlaps[0][1]:.0%}); risk för dubbelräkning."
        elif enough and math.isfinite(edge) and edge>=promote_edge:
            action="PROMOTE CANDIDATE"
            reason=f"Median edge {edge:+.1%} mot kontroll med {n} signal- och {ctl} kontrollutfall."
        elif enough and math.isfinite(edge) and edge<=retire_edge:
            action="RETIRE/DOWNWEIGHT CANDIDATE"
            reason=f"Median edge {edge:+.1%} mot kontroll; signalen underpresterar i moget facit."
        else:
            action="KEEP OBSERVING"
            reason="För litet eller för svagt facit för modelländring."
        rows.append({"Signal":sig,"Action":action,"Evidence":f"N {n}/{ctl} · edge {edge:+.1%}" if math.isfinite(edge) else f"N {n}/{ctl}",
                     "Reason":reason})
    return pd.DataFrame(rows,columns=cols)

def governance_summary(actions:pd.DataFrame|None)->str:
    if actions is None or actions.empty:return "För lite point-in-time-data för signalstyrning."
    c=actions["Action"].value_counts().to_dict()
    return (f"{c.get('PROMOTE CANDIDATE',0)} promote · {c.get('MERGE REVIEW',0)} merge review · "
            f"{c.get('RETIRE/DOWNWEIGHT CANDIDATE',0)} retire/downweight · {c.get('KEEP OBSERVING',0)} fortsätt observera. "
            "Detta är nomineringar, inte automatiska modelländringar.")
