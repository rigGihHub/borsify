from __future__ import annotations

"""Discovery Learning Loop.

Turns repeated, point-in-time Missed Winners patterns into conservative *challenger
proposals*. It never changes production discovery quotas, scores, gates or rankings.
The purpose is to say what should be tested next, not to learn directly from the same
outcomes that exposed the miss.
"""

from typing import Any
import math
import pandas as pd

MIN_MISSES_FOR_PROPOSAL = 5
MIN_OVERREPRESENTATION = 1.50

# Proposals deliberately act on the discovery doorway rather than score weights.
_PATTERN_ACTIONS: dict[str, tuple[str, str]] = {
    "Dyra kvalitetsbolag": (
        "Kvalitetschallenger",
        "Reservera en extra kandidatplats för hög kvalitet även när värderingssignalen är svag.",
    ),
    "Vändningscase": (
        "Vändningschallenger",
        "Reservera en extra kandidatplats för förbättrings-/vändningscase innan djupanalysen.",
    ),
    "Hög kvalitet": (
        "Kvalitetschallenger",
        "Öka representationen av bolag med mycket hög kvalitet i kandidatpoolen med en plats.",
    ),
    "Svag värderingssignal": (
        "Värderingstolerans-challenger",
        "Testa en separat kandidatplats där starka övriga bevis får gå vidare trots svag värderingssignal.",
    ),
    "Svagt marknadsläge": (
        "Timing-challenger",
        "Testa en kandidatplats för starka fundamentala case innan marknadsläget hunnit bekräfta dem.",
    ),
    "Hög risk": (
        "Risk-challenger",
        "Testa en liten separat observationskvot för högre risk i discovery-steget; ordinarie riskgrindar ligger kvar senare.",
    ),
    "Låg datatäckning": (
        "Datatäckningschallenger",
        "Skicka ett fåtal låg-datatäckningscase till datakomplettering före bortsortering, inte direkt till köpbedömning.",
    ),
}


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else float("nan")
    except Exception:
        return float("nan")


def build_discovery_learning_proposals(
    pattern_table: pd.DataFrame,
    min_misses: int = MIN_MISSES_FOR_PROPOSAL,
    min_overrepresentation: float = MIN_OVERREPRESENTATION,
) -> pd.DataFrame:
    """Create pre-change challenger proposals from sufficiently strong miss patterns.

    Only already-frozen diagnostic aggregates are consumed. No current stock data is
    consulted and nothing is written back to the production discovery model.
    """
    cols = [
        "pattern", "challenger", "proposal", "misses", "overrepresentation",
        "median_return", "status", "next_step",
    ]
    if pattern_table is None or pattern_table.empty:
        return pd.DataFrame(columns=cols)

    rows: list[dict[str, Any]] = []
    for _, row in pattern_table.iterrows():
        pattern = str(row.get("pattern", "")).strip()
        if pattern not in _PATTERN_ACTIONS:
            continue
        misses = int(_num(row.get("misses"))) if math.isfinite(_num(row.get("misses"))) else 0
        over = _num(row.get("overrepresentation"))
        median_return = _num(row.get("median_return"))
        strong = misses >= int(min_misses) and math.isfinite(over) and over >= float(min_overrepresentation)
        challenger, proposal = _PATTERN_ACTIONS[pattern]
        status = "Redo för prospektiv challenger" if strong else "Samla mer underlag"
        next_step = (
            "Frys challenger-definitionen och testa endast på nya framtida observationer. Ingen produktionsändring ännu."
            if strong
            else f"Kräver minst {int(min_misses)} missar och {float(min_overrepresentation):.2f}× överrepresentation innan challenger registreras."
        )
        rows.append({
            "pattern": pattern,
            "challenger": challenger,
            "proposal": proposal,
            "misses": misses,
            "overrepresentation": over,
            "median_return": median_return,
            "status": status,
            "next_step": next_step,
        })

    out = pd.DataFrame(rows, columns=cols)
    if out.empty:
        return out
    # Ready proposals first; deterministic strongest evidence ordering after that.
    out["__ready"] = out["status"].eq("Redo för prospektiv challenger").astype(int)
    out = out.sort_values(["__ready", "misses", "overrepresentation", "pattern"], ascending=[False, False, False, True])
    return out.drop(columns="__ready").reset_index(drop=True)


def discovery_learning_summary(proposals: pd.DataFrame) -> dict[str, Any]:
    if proposals is None or proposals.empty:
        return {
            "status": "Bygger underlag",
            "count": 0,
            "text": "Inga discovery-förändringar föreslås ännu. Borsify väntar på återkommande prospektiva missmönster.",
        }
    ready = proposals[proposals["status"].eq("Redo för prospektiv challenger")]
    if ready.empty:
        return {
            "status": "Samla mer underlag",
            "count": 0,
            "text": "Missmönster finns, men inget är ännu starkt nog för en förregistrerad discovery-challenger.",
        }
    top = ready.iloc[0]
    return {
        "status": "Challengerförslag finns",
        "count": int(len(ready)),
        "text": (
            f"{len(ready)} discovery-challenger(s) har tillräckligt diagnostiskt underlag för att förregistreras. "
            f"Starkast just nu: {top['challenger']} ({top['pattern']}). Produktionen ändras inte automatiskt."
        ),
    }
