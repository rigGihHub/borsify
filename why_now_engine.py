from __future__ import annotations

import math
from typing import Any


def _num(v: Any) -> float:
    try:
        x = float(v)
        return x if math.isfinite(x) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def _finite(v: Any) -> bool:
    return math.isfinite(_num(v))


def build_why_now_assessment(case: dict[str, Any]) -> dict[str, Any]:
    """Combine *fresh change* evidence without creating another score.

    The engine is intentionally evidence-first: it distinguishes reported/estimate
    change, post-report price confirmation and independent external catalysts. It
    never turns a scheduled event or a duplicated inflection/catalyst into a second
    independent reason to buy.
    """
    supports: list[tuple[str, str]] = []
    warnings: list[str] = []

    exp_dir = str(case.get("Förväntningsriktning", "") or "")
    exp_strength = str(case.get("Förväntningsstyrka", "") or "")
    exp_status = str(case.get("Förväntningsförändring", "") or "")
    reported_dir = int(_num(case.get("Förväntning reported direction"))) if _finite(case.get("Förväntning reported direction")) else 0
    analyst_dir = int(_num(case.get("Förväntning analyst direction"))) if _finite(case.get("Förväntning analyst direction")) else 0

    # One expectation/change family, even when both analyst and reported data agree.
    if exp_dir in {"positiv", "positiv_tidigt"}:
        if reported_dir > 0 and analyst_dir > 0:
            supports.append(("Förväntningar + bolagssiffror", exp_status or "Både prognoser och färska siffror förbättras."))
        elif reported_dir > 0:
            supports.append(("Färska bolagssiffror", exp_status or "Bolagets färska siffror förbättras."))
        elif analyst_dir > 0:
            supports.append(("Höjda förväntningar", exp_status or "Analytikernas förväntningar höjs."))
    elif exp_dir in {"negativ", "konflikt"}:
        warnings.append(exp_status or "Färska förväntningar/siffror ger motbevis.")

    # Post-report is independent price confirmation only while still fresh.
    pr_days = _num(case.get("Post-report dagar sedan"))
    pr_support = bool(case.get("Post-report stöd", False))
    pr_warning = bool(case.get("Post-report varning", False))
    pr_status = str(case.get("Post-report status", "") or "")
    if pr_support and _finite(pr_days) and 0 <= pr_days <= 30:
        supports.append(("Rapport + fortsatt kursstöd", pr_status or "Marknaden fortsätter bekräfta senaste rapporten."))
    elif pr_warning and (_finite(pr_days) and pr_days <= 30):
        warnings.append(pr_status or "Kursen bekräftar inte senaste rapporten.")

    # Only catalyst_engine's independent-support flag can create this pillar.
    if bool(case.get("Catalyst Independent Support", False)):
        name = str(case.get("Primary Catalyst", "Extern katalysator") or "Extern katalysator")
        timing = str(case.get("Catalyst Timing", "") or "")
        supports.append(("Oberoende katalysator", f"{name}{' · ' + timing if timing and timing != '—' else ''}"))

    cat_signal = str(case.get("Catalyst Signal", "") or "")
    cat_warnings = str(case.get("Catalyst Warnings", "") or "")
    if cat_signal == "Ny risk måste verifieras först":
        warnings.append("Ny extern risk måste verifieras före köp.")
    if "försäm" in str(case.get("Operativ förändring", "") or "").lower():
        warnings.append(str(case.get("Operativ förändring")))

    # Deduplicate families, preserving order.
    seen = set()
    supports = [x for x in supports if not (x[0] in seen or seen.add(x[0]))]
    warnings = list(dict.fromkeys(w for w in warnings if w))
    count = len(supports)

    if warnings and count == 0:
        status = "Motbevis väger tyngre"
    elif count >= 2 and not warnings:
        status = "Tydligt varför nu"
    elif count >= 2:
        status = "Intressant men motstridigt"
    elif count == 1 and not warnings:
        status = "Ett färskt stöd"
    elif count == 1:
        status = "Svagt/motstridigt varför nu"
    else:
        status = "Inget tydligt varför nu"

    if supports:
        summary = ". ".join(text.rstrip(".") for _, text in supports[:2]) + "."
        if warnings:
            summary += " Men: " + warnings[0].rstrip(".") + "."
    elif warnings:
        summary = "Ingen positiv färsk förändring räcker som stöd. " + warnings[0].rstrip(".") + "."
    else:
        summary = "Borsify kan inte verifiera en tillräckligt färsk förändring som förklarar varför caset är intressant just nu."

    return {
        "Why Now Status": status,
        "Why Now Summary": summary,
        "Why Now Evidence Count": count,
        "Why Now Evidence Families": "; ".join(name for name, _ in supports) if supports else "inga verifierade färska stöd",
        "Why Now Contradiction Count": len(warnings),
        "Why Now Warning": warnings[0] if warnings else "ingen tydlig färsk motsägelse",
        "Why Now Has Independent Catalyst": bool(case.get("Catalyst Independent Support", False)),
    }
