from __future__ import annotations

from typing import Any
import pandas as pd

from research_kill_promote_queue import ACTION_REVIEW, ACTION_PROMOTE

CHECK_PENDING = "Ej verifierad"
CHECK_NA = "Ej aktuell"
DECISION_HOLD = "Pausa promotion – utred"
DECISION_REVIEW = "Kandidat för manuell promotion-prövning"


def _as_int(value: Any) -> int:
    try:
        return int(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])
    except Exception:
        return 0


def build_review_dossiers(queue: pd.DataFrame) -> pd.DataFrame:
    """Create conservative review dossiers for hypotheses that need human review.

    The dossier is governance-only. It never promotes, kills, pauses or mutates a
    production signal automatically. Checks that are not measured by the queue are
    explicitly marked as unverified rather than inferred.
    """
    columns = [
        "Hypotes", "Familj", "Åtgärd", "Rekommendation", "Evidensläge",
        "Mogna horisonter", "Största sample", "Regimrobusthet", "Signalöverlapp", "Incrementellt värde",
        "Kostnad/omsättning", "Out-of-sample", "Datakvalitet", "Blockerare", "Nästa beslut",
    ]
    if queue is None or queue.empty:
        return pd.DataFrame(columns=columns)

    selected = queue[queue.get("Åtgärd", pd.Series(dtype=str)).isin([ACTION_REVIEW, ACTION_PROMOTE])].copy()
    if selected.empty:
        return pd.DataFrame(columns=columns)

    rows: list[dict[str, Any]] = []
    for _, row in selected.iterrows():
        action = str(row.get("Åtgärd", ""))
        horizons = _as_int(row.get("Mogna horisonter", 0))
        sample = _as_int(row.get("Största sample", 0))
        status = str(row.get("Status", "—"))

        if action == ACTION_REVIEW:
            recommendation = DECISION_HOLD
            evidence = (
                f"Prospektiva utfall har status '{status}'. Det räcker för kritisk granskning, "
                "men inte för automatisk kill eftersom orsak och robusthet ännu inte är verifierade."
            )
            next_decision = "Avgör manuellt om hypotesen ska fortsätta samla data, pausas eller avvecklas efter metodkontrollerna."
        else:
            recommendation = DECISION_REVIEW
            evidence = (
                f"Preliminärt stöd med {horizons} mogna horisont(er) och största oberoende sample {sample}. "
                "Det gör hypotesen granskningsbar, inte produktionsgodkänd."
            )
            next_decision = "Genomför samtliga blockerande kontroller. Endast därefter får explicit manuell promotion övervägas."

        blockers = ["regimrobusthet", "signalöverlapp", "inkrementellt värde", "kostnad/omsättning", "datakvalitet"]
        if horizons < 2:
            blockers.append("fler mogna horisonter")
        if sample < 30:
            blockers.append("större oberoende sample")

        rows.append({
            "Hypotes": str(row.get("Hypotes", "—")),
            "Familj": str(row.get("Familj", "—")),
            "Åtgärd": action,
            "Rekommendation": recommendation,
            "Evidensläge": evidence,
            "Mogna horisonter": horizons,
            "Största sample": sample,
            "Regimrobusthet": CHECK_PENDING,
            "Signalöverlapp": CHECK_PENDING,
            "Incrementellt värde": CHECK_PENDING,
            "Kostnad/omsättning": CHECK_PENDING,
            "Out-of-sample": "Prospektiv PIT-evidens finns" if horizons > 0 else CHECK_PENDING,
            "Datakvalitet": CHECK_PENDING,
            "Blockerare": ", ".join(blockers),
            "Nästa beslut": next_decision,
        })

    return pd.DataFrame(rows, columns=columns)


def dossier_summary(dossiers: pd.DataFrame) -> dict[str, Any]:
    if dossiers is None or dossiers.empty:
        return {
            "status": "Ingen dossier ännu",
            "text": "Ingen hypotes är just nu mogen för kritisk granskning eller promotion-granskning. Fortsätt samla prospektiv data.",
        }
    review = int(dossiers["Åtgärd"].eq(ACTION_REVIEW).sum())
    promote = int(dossiers["Åtgärd"].eq(ACTION_PROMOTE).sum())
    if review:
        return {
            "status": ACTION_REVIEW,
            "text": f"{review} dossier(er) kräver kritisk granskning. {promote} promotion-kandidat(er) finns, men ingen får gå före en olöst negativ hypotes.",
        }
    return {
        "status": ACTION_PROMOTE,
        "text": f"{promote} dossier(er) är redo för metodisk promotion-granskning. Alla blockerande kontroller måste verifieras manuellt före någon produktionsändring.",
    }
