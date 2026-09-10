from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class HorizonSignal:
    label: str
    short: str
    explanation: str


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _score_column(horizon: str) -> str:
    return {
        "medium": "Mellan Score",
        "year": "Års Score",
        "lifetime": "Livstid Score",
    }[horizon]


def action_signal(row: pd.Series | dict[str, Any], horizon: str, rank: int = 1) -> HorizonSignal:
    """Turn an already eligible Borsify case into a plain-language action signal.

    This is deliberately a presentation layer. It does not make a rejected stock
    eligible, change a score or alter ranking. Missing evidence can only make the
    wording more cautious, never stronger.
    """
    score = _num(row.get(_score_column(horizon)))
    readiness = _num(row.get("Case Readiness"))
    coverage = _num(row.get("Datatäckning"))
    valuation = _num(row.get("Värdering"))
    relative = _num(row.get("Relativ styrka"))
    overextended = bool(row.get("För långt gången") is True)

    strong_evidence = (
        np.isfinite(readiness) and readiness >= 72
        and np.isfinite(coverage) and coverage >= 0.78
    )
    solid_evidence = (
        np.isfinite(readiness) and readiness >= 64
        and (not np.isfinite(coverage) or coverage >= 0.68)
    )

    if horizon == "medium":
        if overextended:
            return HorizonSignal("AVVAKTA", "Vänta på bättre läge", "Caset är intressant men kursen har redan gått för långt för ett färskt kortsiktigt köp.")
        if np.isfinite(score) and score >= 74 and strong_evidence and (not np.isfinite(relative) or relative >= 50):
            return HorizonSignal("KÖP NU", "Starkast läge nu", "Både det kortsiktiga caset och underlaget är starka. Borsify ser ingen tydlig anledning att vänta.")
        if np.isfinite(score) and score >= 68 and solid_evidence:
            return HorizonSignal("KÖP", "Köpbar nu", "Aktien klarar köpkraven, men signalen är inte lika stark som för ett tydligt Köp nu-läge.")
        return HorizonSignal("BEVAKA", "Intressant, men inte bråttom", "Caset klarar listan men underlaget eller timingen är inte stark nog för en tydligare köpsignal.")

    if horizon == "year":
        if np.isfinite(score) and score >= 75 and strong_evidence:
            return HorizonSignal("KÖP / ÄG", "Starkt 3–12 månaderscase", "Bolaget har ett starkt års-case med tillräckligt bra underlag för att Borsify ska föredra köp eller fortsatt ägande.")
        if np.isfinite(score) and score >= 68 and solid_evidence:
            return HorizonSignal("BYGG POSITION", "Köp stegvis", "Caset är attraktivt på upp till ett år, men det finns inte skäl att behandla tidpunkten som exakt.")
        return HorizonSignal("BEVAKA", "Bra case, svagare övertygelse", "Aktien är intressant på upp till ett år men bör följas innan större position tas.")

    if horizon == "lifetime":
        # Lifetime recommendations should be especially conservative about price.
        if np.isfinite(score) and score >= 78 and strong_evidence and (not np.isfinite(valuation) or valuation >= 55):
            return HorizonSignal("KÖP / ÄG LÅNGSIKTIGT", "Stark livstidskandidat", "Bolagets uthålliga kvalitet och riskprofil är starka nog för mycket lång ägarhorisont, till ett pris som inte ser uppenbart ansträngt ut.")
        if np.isfinite(score) and score >= 72 and solid_evidence:
            if np.isfinite(valuation) and valuation < 50:
                return HorizonSignal("BEVAKA PRISET", "Bra bolag, priset avgör", "Bolaget passar den långa horisonten bättre än dagens värdering. Borsify vill inte blanda ihop ett bra bolag med ett bra köppris.")
            return HorizonSignal("BYGG LÅNGSIKTIGT", "Köp stegvis över tid", "Bolaget har en stark långsiktig profil, men en mycket lång investering behöver inte tajmas till en enskild dag.")
        return HorizonSignal("BEVAKA", "Inte stark nog ännu", "Bolaget finns högt i rankingen men Borsify har inte tillräckligt starkt underlag för en tydligare livstidssignal.")

    raise ValueError(f"Okänd horisont: {horizon}")


def add_action_signals(df: pd.DataFrame, horizon: str) -> pd.DataFrame:
    if df is None or df.empty:
        return df.copy() if isinstance(df, pd.DataFrame) else pd.DataFrame()
    out = df.copy()
    signals = [action_signal(row, horizon, rank=i + 1) for i, (_, row) in enumerate(out.iterrows())]
    out["Signal"] = [s.label for s in signals]
    out["Signal kort"] = [s.short for s in signals]
    out["Signal förklaring"] = [s.explanation for s in signals]
    return out


def signal_legend(horizon: str) -> list[tuple[str, str]]:
    if horizon == "medium":
        return [
            ("KÖP NU", "Starkt case och stark timing just nu."),
            ("KÖP", "Köpkraven är uppfyllda men läget är mindre brådskande."),
            ("BEVAKA", "Intressant case, men Borsify vill se starkare timing eller underlag."),
            ("AVVAKTA", "Bra case kan finnas, men prisrörelsen gör att Borsify hellre väntar."),
        ]
    if horizon == "year":
        return [
            ("KÖP / ÄG", "Starkt case för ungefär 3–12 månader."),
            ("BYGG POSITION", "Köp stegvis i stället för att försöka träffa en exakt dag."),
            ("BEVAKA", "Intressant men ännu inte tillräckligt starkt för tydligare handling."),
        ]
    if horizon == "lifetime":
        return [
            ("KÖP / ÄG LÅNGSIKTIGT", "Mycket stark långsiktig kandidat till rimligt pris."),
            ("BYGG LÅNGSIKTIGT", "Stark kandidat där stegvisa köp passar bättre."),
            ("BEVAKA PRISET", "Bra bolag, men värderingen gör att priset bör följas."),
            ("BEVAKA", "Högt rankad men inte stark nog för en livstidssignal ännu."),
        ]
    return []
