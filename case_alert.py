from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        out = float(value)
        return out if np.isfinite(out) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _text(mapping: Mapping[str, Any] | None, key: str, default: str = "") -> str:
    if not mapping:
        return default
    value = mapping.get(key, default)
    return str(value) if value is not None else default


def evaluate_case_alert(
    journal: Mapping[str, Any] | None,
    breaker: Mapping[str, Any] | None,
    idea: Mapping[str, Any] | pd.Series | None,
) -> dict[str, Any]:
    """Combine internal case deterioration with external event context.

    This is a triage layer, not a buy/sell model. External headlines never change
    Borsify Score. Ambiguous company events are intentionally labelled as needing
    verification rather than being guessed positive or negative.
    """
    journal = dict(journal or {})
    breaker = dict(breaker or {})
    idea_map: Mapping[str, Any] = idea.to_dict() if isinstance(idea, pd.Series) else (idea or {})

    journal_tone = _text(journal, "tone", "neutral")
    journal_status = _text(journal, "status", "Historiken byggs upp")
    score_delta = _num(journal.get("score_delta"))
    journal_weaker = journal_tone == "negative" or (np.isfinite(score_delta) and score_delta <= -5)

    breaker_tone = _text(breaker, "tone", "neutral")
    breaker_status = _text(breaker, "status", "Inga case-breakers satta")
    breaker_triggered = breaker_tone == "negative" or bool(breaker.get("triggered"))
    breaker_near = breaker_tone == "warning" or bool(breaker.get("near"))

    event = _text(idea_map, "Huvudhändelse", "")
    impact = _text(idea_map, "Case Impact", "")
    impact_level = _num(idea_map.get("Case Impact Nivå"))
    pulse = _text(idea_map, "Mediepuls", "")
    media_sources = _num(idea_map.get("Mediekällor"))
    mentions_24h = _num(idea_map.get("Omnämnanden 24h"))

    has_external = bool(event or impact or pulse)
    negative_external = event == "Vinstvarning / tydlig försämring" or impact == "Ny risk – kontrollera direkt"
    material_external = has_external and np.isfinite(impact_level) and impact_level >= 2
    high_impact_external = has_external and np.isfinite(impact_level) and impact_level >= 3

    reasons: list[str] = []
    if journal_weaker:
        if np.isfinite(score_delta):
            reasons.append(f"Borsifys mätbild har försvagats ({score_delta:+.1f} scorepoäng sedan start).")
        else:
            reasons.append("Borsifys mätbild har försvagats sedan du började följa aktien.")
    if breaker_triggered:
        reasons.append("Minst en av dina egna case-breaker-regler är utlöst.")
    elif breaker_near:
        reasons.append("Minst en av dina egna case-breaker-regler ligger nära gränsen.")
    if negative_external:
        reasons.append("Mediabevakningen har hittat en vinstvarning eller annan tydlig försämring som behöver verifieras i originalkällan.")
    elif material_external:
        reasons.append(f"En ny händelse av typen {event or 'bolagshändelse'} kan påverka investeringscaset, men riktningen är inte verifierad från rubriken ensam.")

    if negative_external and (journal_weaker or breaker_triggered):
        return {
            "status": "Granska nu",
            "tone": "critical",
            "priority": 3,
            "summary": "Borsifys egen mätbild visar samtidigt svaghet som mediabevakningen har hittat en ny tydlig risk. Det är en stark signal att läsa originalkällan och ompröva antagandena bakom caset – inte en automatisk säljorder.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if breaker_triggered and material_external:
        return {
            "status": "Två saker kräver kontroll",
            "tone": "critical",
            "priority": 3,
            "summary": "En egen case-breaker är utlöst samtidigt som en ny bolagshändelse kan ändra caset. Händelsens riktning måste fortfarande verifieras i originalkällan.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if journal_weaker and material_external:
        return {
            "status": "Caset försvagas + ny viktig händelse",
            "tone": "warning",
            "priority": 2,
            "summary": "Borsifys mätbild har försvagats och det finns samtidigt en ny bolagshändelse som kan vara relevant. Läs källan innan du avgör om händelsen förstärker eller förklarar förändringen.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if negative_external:
        return {
            "status": "Ny extern risk",
            "tone": "warning",
            "priority": 2,
            "summary": "Mediabevakningen har hittat en tydlig riskhändelse. Äldre nyckeltal kan ännu inte ha hunnit fånga effekten, så originalkällan bör kontrolleras först.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if breaker_triggered:
        return {
            "status": "Case-breaker utlöst",
            "tone": "warning",
            "priority": 2,
            "summary": "Något du själv sagt skulle försvaga investeringsidén har inträffat. Granska caset på nytt, även om mediabevakningen inte visar någon ny tydlig händelse.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if high_impact_external:
        return {
            "status": "Ny viktig bolagshändelse",
            "tone": "info",
            "priority": 1,
            "summary": "En ny händelse kan påverka framtida vinst, risk eller finansiering. Borsify gissar inte riktningen från rubriken – läs originalkällan och uppdatera caset därefter.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if breaker_near and material_external:
        return {
            "status": "Värt en extra kontroll",
            "tone": "warning",
            "priority": 1,
            "summary": "En egen gräns ligger nära samtidigt som en ny relevant bolagshändelse har dykt upp. Det räcker för en extra kontroll, men inte för en slutsats om köp eller sälj.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if journal_weaker:
        return {
            "status": "Mätbilden har försvagats",
            "tone": "warning",
            "priority": 1,
            "summary": "Borsifys egna mätpunkter har blivit svagare sedan starten. Det finns ingen ny verifierad extern risk i den hämtade bevakningen, men caset är värt att läsa om.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    if has_external and (pulse in {"Ökad uppmärksamhet", "Aktivt just nu", "Nytt omnämnande"} or (np.isfinite(mentions_24h) and mentions_24h > 0)):
        breadth = f" från {int(media_sources)} mediekälla/källor" if np.isfinite(media_sources) and media_sources > 0 else ""
        return {
            "status": "Nytt att läsa – inget internt larm",
            "tone": "neutral",
            "priority": 0,
            "summary": f"Aktien har fått ny extern uppmärksamhet{breadth}, men Borsifys interna kontroller visar ingen samtidig tydlig försämring. Behandla det som ett uppslag, inte som en signal.",
            "reasons": reasons,
            "event": event,
            "journal_status": journal_status,
            "breaker_status": breaker_status,
        }

    return {
        "status": "Inget nytt samlat larm",
        "tone": "positive" if breaker_tone == "positive" and journal_tone != "negative" else "neutral",
        "priority": 0,
        "summary": "Borsify ser just nu ingen kombination av intern försämring och ny extern händelse som behöver lyftas särskilt.",
        "reasons": reasons,
        "event": event,
        "journal_status": journal_status,
        "breaker_status": breaker_status,
    }
