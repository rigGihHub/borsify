from __future__ import annotations

from typing import Any
import pandas as pd

from prospective_signal_scorecard import STATUS_REVIEW, STATUS_SUPPORT, STATUS_MIXED, STATUS_WAIT

ACTION_REVIEW = "Granska kritiskt"
ACTION_PROMOTE = "Promotion-granskning"
ACTION_COLLECT = "Samla mer data"


def _as_int(value: Any) -> int:
    try:
        return int(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])
    except Exception:
        return 0


def build_research_queue(scorecard: pd.DataFrame, promotion_min_horizons: int = 2, promotion_min_sample: int = 30) -> pd.DataFrame:
    """Turn the prospective scorecard into a research work queue.

    Governance only. The queue never changes a production score, gate, weight, signal,
    champion or policy automatically.
    """
    columns = ["Prioritet", "Åtgärd", "Hypotes", "Familj", "Status", "Mogna horisonter", "Största sample", "Varför", "Nästa kontroll"]
    if scorecard is None or scorecard.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, row in scorecard.iterrows():
        status = str(row.get("Status", STATUS_WAIT))
        horizons = _as_int(row.get("Mogna horisonter", 0))
        sample = _as_int(row.get("Största sample", 0))
        hypothesis = str(row.get("Hypotes", "—"))
        family = str(row.get("Familj", "—"))

        if status == STATUS_REVIEW:
            action = ACTION_REVIEW
            priority = 1
            why = "Prospektiva utfall går åt fel håll. Hypotesen ska granskas innan mer betydelse övervägs."
            nxt = "Kontrollera datakvalitet, kohorter, horisonter och om hypotesen bör pausas eller dödas. Ingen automatisk borttagning."
        elif status == STATUS_SUPPORT and horizons >= promotion_min_horizons and sample >= promotion_min_sample:
            action = ACTION_PROMOTE
            priority = 2
            why = "Preliminärt stöd finns över tillräckligt många mogna horisonter och ett större oberoende sample."
            nxt = "Gör en separat promotion-granskning: robusthet, regimer, överlapp, kostnader och out-of-sample innan eventuell modelländring."
        else:
            action = ACTION_COLLECT
            priority = 3
            if status == STATUS_SUPPORT:
                why = "Signalbilden är lovande men underlaget är ännu för tunt för promotion-granskning."
            elif status == STATUS_MIXED:
                why = "Mogna utfall finns men riktningen är ännu oklar."
            else:
                why = "För få mogna point-in-time-utfall finns ännu."
            missing = []
            if horizons < promotion_min_horizons:
                missing.append(f"minst {promotion_min_horizons} mogna horisonter")
            if sample < promotion_min_sample:
                missing.append(f"minst {promotion_min_sample} oberoende case")
            nxt = "Fortsätt samla frysta utfall"
            if missing:
                nxt += " mot " + " och ".join(missing)
            nxt += ". Ändra inte produktionsmodellen under tiden."

        rows.append({
            "Prioritet": priority,
            "Åtgärd": action,
            "Hypotes": hypothesis,
            "Familj": family,
            "Status": status,
            "Mogna horisonter": horizons,
            "Största sample": sample,
            "Varför": why,
            "Nästa kontroll": nxt,
        })

    out = pd.DataFrame(rows, columns=columns)
    return out.sort_values(["Prioritet", "Största sample", "Hypotes"], ascending=[True, False, True], kind="stable").reset_index(drop=True)


def research_queue_summary(queue: pd.DataFrame) -> dict[str, Any]:
    if queue is None or queue.empty:
        return {"status": ACTION_COLLECT, "text": "Forskningskön är tom eftersom inget prospektivt scorecard finns ännu."}
    reviews = int(queue["Åtgärd"].eq(ACTION_REVIEW).sum())
    promotes = int(queue["Åtgärd"].eq(ACTION_PROMOTE).sum())
    collects = int(queue["Åtgärd"].eq(ACTION_COLLECT).sum())
    if reviews:
        return {"status": ACTION_REVIEW, "text": f"{reviews} hypotes(er) behöver kritisk granskning först. {promotes} är promotion-kandidat(er) och {collects} behöver mer data."}
    if promotes:
        return {"status": ACTION_PROMOTE, "text": f"{promotes} hypotes(er) är mogna för promotion-granskning. {collects} behöver fortfarande mer data."}
    return {"status": ACTION_COLLECT, "text": f"Alla {collects} hypotes(er) behöver mer prospektiv data innan nästa styrningsbeslut."}
