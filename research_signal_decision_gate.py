from __future__ import annotations

from typing import Any
import pandas as pd

from research_kill_promote_queue import ACTION_REVIEW, ACTION_PROMOTE
from research_review_dossier import CHECK_PENDING

DECISION_COLLECT = "Fortsätt samla data"
DECISION_PAUSE = "Pausa / avvisa-kandidat"
DECISION_PROMOTE = "Redo för manuell promotion-prövning"

MIN_HORIZONS = 2
MIN_SAMPLE = 30


def _as_int(value: Any) -> int:
    try:
        return int(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])
    except Exception:
        return 0


def _blockers(value: Any) -> list[str]:
    return [x.strip() for x in str(value or "").split(",") if x.strip()]


def signal_decision(row: pd.Series | dict[str, Any]) -> dict[str, Any]:
    """Collapse a completed research dossier into one conservative governance decision.

    This gate never mutates production.  Promotion means only that the hypothesis has
    passed the currently implemented research checks and may be reviewed manually.
    A pause/reject result is likewise a research-governance recommendation, not an
    automatic deletion or production kill.
    """
    action = str(row.get("Åtgärd", ""))
    horizons = _as_int(row.get("Mogna horisonter", 0))
    sample = _as_int(row.get("Största sample", 0))
    blockers = _blockers(row.get("Blockerare", ""))

    regime = str(row.get("Regimrobusthet", CHECK_PENDING))
    overlap = str(row.get("Signalöverlapp", CHECK_PENDING))
    incremental = str(row.get("Incrementellt värde", CHECK_PENDING))
    cost = str(row.get("Kostnad/omsättning", CHECK_PENDING))
    oos = str(row.get("Out-of-sample", CHECK_PENDING))
    quality = str(row.get("Datakvalitet", CHECK_PENDING))

    fatal_reasons: list[str] = []
    if action == ACTION_REVIEW:
        fatal_reasons.append("prospektiva utfall ligger redan i kritisk granskningskö")
    if regime == "Ifrågasatt i flera regimer":
        fatal_reasons.append("hypotesen går åt fel håll i flera marknadsregimer")
    if incremental == "Inget inkrementellt värde":
        fatal_reasons.append("inget inkrementellt värde efter matchning")
    if cost == "Kostnad/omsättning ifrågasatt":
        fatal_reasons.append("utfallet är kostnads-/omsättningskänsligt")
    if quality == "Datakvalitet ifrågasatt":
        fatal_reasons.append("datakvaliteten är ifrågasatt")

    if fatal_reasons:
        return {
            "Beslut": DECISION_PAUSE,
            "Gate": "STOPP",
            "Skäl": "; ".join(fatal_reasons),
            "Kvarvarande blockerare": ", ".join(blockers),
            "Manuell åtgärd": "Pausa promotion. Granska orsak och datakvalitet innan hypotesen eventuellt fortsätter eller avvecklas. Ingen automatisk kill.",
        }

    missing_reasons: list[str] = []
    if action != ACTION_PROMOTE:
        missing_reasons.append("hypotesen är inte i promotion-granskning")
    if horizons < MIN_HORIZONS:
        missing_reasons.append(f"bara {horizons} mogen horisont(er); minst {MIN_HORIZONS} krävs")
    if sample < MIN_SAMPLE:
        missing_reasons.append(f"största sample är {sample}; minst {MIN_SAMPLE} krävs")
    if blockers:
        missing_reasons.append("blockerande kontroller återstår: " + ", ".join(blockers))

    required = {
        "regimrobusthet": regime == "Stöd i flera regimer",
        "signalöverlapp": overlap in {"Lågt överlapp", "Måttligt överlapp"},
        "inkrementellt värde": incremental == "Tydligt inkrementellt stöd",
        "kostnad/omsättning": cost == "Kostnad/omsättning verifierad",
        "out-of-sample": oos == "Prospektiv PIT-evidens finns",
        "datakvalitet": quality == "Datakvalitet verifierad",
    }
    for name, ok in required.items():
        if not ok:
            observed = {
                "regimrobusthet": regime,
                "signalöverlapp": overlap,
                "inkrementellt värde": incremental,
                "kostnad/omsättning": cost,
                "out-of-sample": oos,
                "datakvalitet": quality,
            }[name]
            if observed not in {CHECK_PENDING, "", "nan"}:
                missing_reasons.append(f"{name} når inte promotionskravet ({observed})")
            elif name not in blockers:
                missing_reasons.append(f"{name} är inte verifierad")

    # High overlap is not evidence that a signal is harmful, but it fails the uniqueness
    # requirement for promotion and must continue in research rather than be rejected.
    if overlap == "Högt överlapp" and "signalöverlapp" not in ", ".join(missing_reasons):
        missing_reasons.append("högt signalöverlapp; unikt informationsvärde är inte visat")

    if missing_reasons:
        return {
            "Beslut": DECISION_COLLECT,
            "Gate": "VÄNTA",
            "Skäl": "; ".join(dict.fromkeys(missing_reasons)),
            "Kvarvarande blockerare": ", ".join(blockers),
            "Manuell åtgärd": "Fortsätt samla prospektiv PIT-data och slutför saknade/otillräckliga kontroller. Ingen modelländring.",
        }

    return {
        "Beslut": DECISION_PROMOTE,
        "Gate": "PASS",
        "Skäl": (
            "Minimikrav för mognad är uppfyllda och samtliga centrala dossierkontroller passerar: "
            "flera regimer, begränsat överlapp, tydligt inkrementellt stöd, kostnadsrobusthet, "
            "prospektiv PIT-evidens och verifierad datakvalitet."
        ),
        "Kvarvarande blockerare": "",
        "Manuell åtgärd": "Genomför uttrycklig manuell promotion-prövning. PASS är inte ett automatiskt produktionsbeslut.",
    }


def apply_signal_decision_gate(dossiers: pd.DataFrame) -> pd.DataFrame:
    if dossiers is None or dossiers.empty:
        return dossiers.copy() if isinstance(dossiers, pd.DataFrame) else pd.DataFrame()
    out = dossiers.copy()
    decisions = pd.DataFrame([signal_decision(row) for _, row in out.iterrows()], index=out.index)
    for col in decisions.columns:
        out[col] = decisions[col]
    return out


def decision_gate_summary(dossiers: pd.DataFrame) -> dict[str, Any]:
    if dossiers is None or dossiers.empty or "Beslut" not in dossiers.columns:
        return {"status": "Ingen signal redo", "text": "Ingen forskningshypotes har ännu nått Signal Decision Gate."}
    pause = int(dossiers["Beslut"].eq(DECISION_PAUSE).sum())
    promote = int(dossiers["Beslut"].eq(DECISION_PROMOTE).sum())
    collect = int(dossiers["Beslut"].eq(DECISION_COLLECT).sum())
    if pause:
        return {
            "status": DECISION_PAUSE,
            "text": f"{pause} hypotes(er) bör pausas och granskas kritiskt. {promote} är redo för manuell promotion-prövning och {collect} behöver mer data. Negativa forskningsutfall prioriteras före promotion.",
        }
    if promote:
        return {
            "status": DECISION_PROMOTE,
            "text": f"{promote} hypotes(er) har passerat hela forskningsgaten och är redo för manuell promotion-prövning. {collect} behöver mer data. Ingen produktionsändring sker automatiskt.",
        }
    return {
        "status": DECISION_COLLECT,
        "text": f"{collect} hypotes(er) behöver mer prospektiv data eller starkare robusthetsbevis innan promotion kan övervägas.",
    }
