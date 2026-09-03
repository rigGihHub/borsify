from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd


def _num(value: Any) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def _norm(text: str) -> str:
    text = (text or '').lower()
    repl = str.maketrans({'å':'a','ä':'a','ö':'o','é':'e','ü':'u'})
    text = text.translate(repl)
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9%+\- ]+', ' ', text)).strip()


def _to_ts(value: Any) -> pd.Timestamp | None:
    try:
        ts = pd.to_datetime(value, utc=True)
        if isinstance(ts, pd.DatetimeIndex):
            ts = ts[0] if len(ts) else pd.NaT
        if pd.isna(ts):
            return None
        return pd.Timestamp(ts)
    except Exception:
        return None


def _days_until(value: Any, now: pd.Timestamp | None = None) -> int | None:
    ts = _to_ts(value)
    if ts is None:
        return None
    now = now or pd.Timestamp.now(tz='UTC')
    if now.tzinfo is None:
        now = now.tz_localize('UTC')
    return int((ts.normalize() - now.normalize()).days)


def _news_age_days(value: Any, now: pd.Timestamp | None = None) -> int | None:
    ts = _to_ts(value)
    if ts is None:
        return None
    now = now or pd.Timestamp.now(tz='UTC')
    if now.tzinfo is None:
        now = now.tz_localize('UTC')
    return max(0, int((now.normalize() - ts.normalize()).days))


POSITIVE_NEWS_RULES = [
    ('Höjd prognos/guidance', ('raises guidance','raised guidance','raises outlook','raised outlook','hojer prognos','hojd prognos','hojer utsikter','guidance raised')),
    ('Order/kontrakt', ('wins contract','won contract','new contract','awarded contract','order worth','order value','far order','vinner kontrakt','nytt kontrakt','order vard')),
    ('Regulatoriskt godkännande', ('regulatory approval','approved by','fda approval','ema approval','godkannande','godkand av','myndighetsgodkannande')),
    ('Återköp', ('share buyback','stock buyback','repurchase program','aterkop','aterkopsprogram')),
    ('Insiderköp', ('insider buys','insider purchase','director buys','ceo buys','vd koper','insiderkop')),
]

UNCERTAIN_NEWS_RULES = [
    ('Rapport/resultat', ('earnings','results','report','rapport','delarsrapport','bokslut')),
    ('Produkt/lansering', ('launches','launch','new product','lanserar','lansering','ny produkt')),
    ('Förvärv/bud', ('acquisition','acquires','merger','takeover','bid for','forvarv','koper bolag','bud pa')),
    ('Utdelning', ('dividend','utdelning')),
]

NEGATIVE_NEWS_RULES = [
    ('Sänkt prognos/vinstvarning', ('profit warning','cuts guidance','cut guidance','lowers guidance','lowered outlook','vinstvarning','sanker prognos','sankt prognos')),
    ('Emission/finansieringsrisk', ('rights issue','share issue','equity raise','new shares','nyemission','foretradesemission','riktad emission')),
]


def classify_news_catalyst(title: str) -> tuple[str, str, int]:
    """Return (type, direction, evidence strength) from a headline only.

    Headline interpretation is deliberately conservative. It never estimates economic
    magnitude and uncertain corporate events stay neutral until source details are read.
    """
    t = _norm(title)
    for label, terms in NEGATIVE_NEWS_RULES:
        if any(_norm(term) in t for term in terms):
            return label, 'negative', 3
    for label, terms in POSITIVE_NEWS_RULES:
        if any(_norm(term) in t for term in terms):
            return label, 'positive', 3
    for label, terms in UNCERTAIN_NEWS_RULES:
        if any(_norm(term) in t for term in terms):
            return label, 'uncertain', 2
    return 'Oklart', 'uncertain', 0


def build_catalyst_assessment(case: dict[str, Any] | pd.Series, events: dict[str, Any] | None = None,
                              now: pd.Timestamp | None = None) -> dict[str, Any]:
    """Build explicit, evidence-aware catalysts for a long-term case.

    Catalysts are not treated as a guarantee of price appreciation. The output separates
    scheduled/observable events from inferred operating inflections and labels headline-only
    evidence so it cannot masquerade as verified financial data.
    """
    events = events or {}
    now = now or pd.Timestamp.now(tz='UTC')
    candidates: list[dict[str, Any]] = []
    warnings: list[str] = []

    # 1) Scheduled report: verified timing when calendar data exists, but direction unknown.
    earnings = events.get('earnings')
    days = _days_until(earnings, now)
    if days is not None and -2 <= days <= 90:
        timing = 'inom en vecka' if 0 <= days <= 7 else ('inom en månad' if 0 <= days <= 31 else 'inom cirka tre månader')
        if days < 0:
            timing = 'nyss rapporterat – kontrollera utfallet'
        candidates.append({
            'name': 'Kommande rapport', 'direction': 'uncertain', 'strength': 2,
            'confidence': 90, 'timing': timing,
            'effect': 'Kan bekräfta eller motbevisa den pågående vinst-/marginaltrenden.',
            'evidence': 'Schemalagt rapportdatum från bolagskalender/datafeed.',
        })

    # 2) Fundamental/estimate inflection: data-derived, not headline-derived.
    infl_signal = str(case.get('Inflection Signal', ''))
    infl_conf = _num(case.get('Inflection Confidence'))
    eps_rev = _num(case.get('EPS-estimat förändring'))
    rev_acc = _num(case.get('Omsättning acceleration'))
    margin_change = _num(case.get('Marginal YoY förändring'))
    fcf_change = _num(case.get('FCF YoY senaste kvartal'))

    if infl_signal in {'Positiv inflektion', 'Tidiga förbättringstecken'}:
        evidence_bits = []
        if np.isfinite(eps_rev) and eps_rev > 0.02:
            evidence_bits.append(f'EPS-estimat +{eps_rev:.1%}')
        if np.isfinite(rev_acc) and rev_acc > 0.02:
            evidence_bits.append(f'omsättning accelererar {rev_acc:+.1%}')
        if np.isfinite(margin_change) and margin_change > 0.01:
            evidence_bits.append(f'marginal förbättras {margin_change:+.1%}')
        if np.isfinite(fcf_change) and fcf_change > 0.10:
            evidence_bits.append('fritt kassaflöde förbättras tydligt')
        candidates.append({
            'name': 'Fundamental inflektion', 'direction': 'positive', 'strength': 3,
            'confidence': int(np.clip(infl_conf if np.isfinite(infl_conf) else 55, 35, 90)),
            'timing': 'nästa 1–2 rapporter',
            'effect': 'Fortsatt förbättring kan tvinga marknaden att höja sina vinst- eller kvalitetsantaganden.',
            'evidence': ', '.join(evidence_bits) if evidence_bits else 'Flera färska förändringssignaler pekar åt rätt håll.',
        })
    elif infl_signal in {'Negativ förändring', 'Tydlig försämring'}:
        warnings.append('Färska estimat/kvartalstrender försämras – positiv katalysator får inte överskugga detta.')

    # 3) Deleveraging / cash-flow inflection from statements.
    debt_change = _num(case.get('Skuldförändring'))
    positive_fcf_share = _num(case.get('Positiv FCF-andel'))
    if np.isfinite(debt_change) and debt_change <= -0.10:
        candidates.append({
            'name': 'Skuldminskning', 'direction': 'positive', 'strength': 2,
            'confidence': 75, 'timing': '6–18 månader',
            'effect': 'Fortsatt skuldminskning kan sänka finansiell risk och förbättra marknadens värdering av bolaget.',
            'evidence': f'Rapporterad skuldtrend cirka {debt_change:+.1%}.',
        })
    if np.isfinite(fcf_change) and fcf_change > 0.20 and (not np.isfinite(positive_fcf_share) or positive_fcf_share >= 0.5):
        candidates.append({
            'name': 'Kassaflödesvändning', 'direction': 'positive', 'strength': 2,
            'confidence': 70, 'timing': 'nästa 1–3 rapporter',
            'effect': 'Om förbättringen håller i sig kan marknaden börja värdera vinsten som mer uthållig och finansieringsrisken som lägre.',
            'evidence': f'FCF senaste kvartalet förändrades cirka {fcf_change:+.1%} år/år.',
        })

    # 4) Headlines are useful triage only when timing is known and reasonably fresh.
    # An undated/old headline must never be presented as "why now".
    negative_headline = False
    for item in (events.get('news') or [])[:5]:
        if not isinstance(item, dict):
            continue
        title = str(item.get('title') or '').strip()
        if not title:
            continue
        label, direction, strength = classify_news_catalyst(title)
        if strength <= 0:
            continue

        age_days = _news_age_days(item.get('published_at'), now)
        provider = str(item.get('provider') or '').strip()
        source_bits = [x for x in [provider, f"{age_days} dagar sedan" if age_days is not None else "datum saknas"] if x]
        source_text = " · ".join(source_bits)

        # Old headlines are context, not current catalysts.
        if age_days is not None and age_days > 30:
            warnings.append(f'Äldre rubrik ({label}, {age_days} dagar): “{title[:120]}”. Räknas inte som aktuell katalysator.')
            continue

        # Missing publication date means we cannot prove recency. Keep it visible as
        # a warning/context item, but do not let it create positive catalyst support.
        if age_days is None:
            if direction == 'negative':
                negative_headline = True
                warnings.append(
                    f'Negativ rubrik utan verifierbart datum ({label}): “{title[:120]}”. '
                    'Risken måste kontrolleras innan ett positivt case får visas som tydligt.'
                )
            else:
                warnings.append(
                    f'Rubrik utan verifierbart datum ({label}): “{title[:120]}”. '
                    'Kan inte användas som ”varför nu”.'
                )
            continue

        fresh = age_days <= 14
        if direction == 'negative':
            negative_headline = True
            warnings.append(
                f'Färsk rubrik kan vara negativ ({label}, {source_text}): “{title[:130]}”. Läs originalkällan.'
            )
            continue

        candidates.append({
            'name': label,
            'direction': direction,
            'strength': strength if fresh else max(1, strength - 1),
            'confidence': (58 if direction == 'positive' else 40) if fresh else 35,
            'timing': f'{age_days} dagar sedan' if age_days > 0 else 'idag',
            'effect': ('Kan ge marknaden ny fundamental information om den ekonomiska betydelsen är stor.'
                       if direction == 'positive' else 'Kan ändra caset, men riktning och ekonomisk effekt kan inte avgöras från rubriken.'),
            'evidence': (
                f'Rubrik i extern källa ({source_text}): “{title[:150]}”. '
                'Rubriken är endast en ledtråd och måste verifieras i originalkällan.'
            ),
            'link': item.get('link'),
            'published_at': item.get('published_at'),
            'provider': provider,
            'age_days': age_days,
            'fresh': bool(fresh),
        })

    # De-duplicate same catalyst type and rank by evidence/direction.
    dedup: dict[str, dict[str, Any]] = {}
    for c in candidates:
        old = dedup.get(c['name'])
        rank = (1 if c['direction'] == 'positive' else 0, c['strength'], c['confidence'])
        old_rank = (-1, -1, -1) if old is None else (1 if old['direction'] == 'positive' else 0, old['strength'], old['confidence'])
        if old is None or rank > old_rank:
            dedup[c['name']] = c
    candidates = sorted(dedup.values(), key=lambda c: (c['direction'] == 'positive', c['strength'], c['confidence']), reverse=True)

    positives = [c for c in candidates if c['direction'] == 'positive']
    scheduled = [c for c in candidates if c['name'] == 'Kommande rapport']
    primary = positives[0] if positives else (scheduled[0] if scheduled else (candidates[0] if candidates else None))

    if negative_headline:
        signal = 'Ny risk måste verifieras först'
    elif positives and any(c['strength'] >= 3 and c['confidence'] >= 55 for c in positives):
        signal = 'Tydlig möjlig katalysator'
    elif positives:
        signal = 'Möjlig katalysator'
    elif scheduled:
        signal = 'Närliggande kontrollpunkt'
    elif candidates:
        signal = 'Händelse att bevaka'
    else:
        signal = 'Ingen tydlig katalysator verifierad'

    positive_strength = max([c['strength'] for c in positives], default=0)
    positive_conf = max([c['confidence'] for c in positives], default=0)
    catalyst_support = signal in {'Tydlig möjlig katalysator', 'Möjlig katalysator'} and not negative_headline

    if primary:
        why_now = f"{primary['name']} · {primary['timing']}. {primary['effect']}"
        primary_name = primary['name']
        primary_timing = primary['timing']
        primary_effect = primary['effect']
        primary_evidence = primary['evidence']
    else:
        why_now = 'Ingen konkret katalysator kan verifieras med tillgänglig data. Ett bra bolag kan därför förbli felprissatt länge.'
        primary_name = 'Ingen verifierad'
        primary_timing = '—'
        primary_effect = 'Ingen tydlig omvärderingsmekanism kan beläggas ännu.'
        primary_evidence = 'Otillräcklig katalysatordata.'

    return {
        'Catalyst Signal': signal,
        'Catalyst Support': bool(catalyst_support),
        'Catalyst Strength': int(positive_strength),
        'Catalyst Confidence': int(positive_conf if positives else (primary.get('confidence', 0) if primary else 0)),
        'Primary Catalyst': primary_name,
        'Catalyst Timing': primary_timing,
        'Catalyst Effect': primary_effect,
        'Catalyst Evidence': primary_evidence,
        'Catalyst Why Now': why_now,
        'Catalyst Warnings': '; '.join(dict.fromkeys(warnings)) if warnings else 'inga tydliga katalysatorrelaterade varningar',
        'Catalyst Candidates': candidates[:4],
    }
