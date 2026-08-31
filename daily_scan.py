"""Borsify scheduled scanner + e-mail digest.

Designed for GitHub Actions or another server-side scheduler.
Required for scanning:
  BORSIFY_SUPABASE_URL
  BORSIFY_SUPABASE_SERVICE_ROLE_KEY

Optional e-mail delivery via Resend:
  BORSIFY_RESEND_API_KEY
  BORSIFY_EMAIL_FROM            e.g. "Borsify <radar@borsify.se>"
  BORSIFY_APP_URL               defaults to https://borsify.se

The service-role key and Resend key must only exist in server/GitHub Secrets.
"""
from __future__ import annotations

import html
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
from supabase import create_client

import app as core

URL = os.getenv("BORSIFY_SUPABASE_URL", "").strip()
KEY = os.getenv("BORSIFY_SUPABASE_SERVICE_ROLE_KEY", "").strip()
PROFILE = os.getenv("BORSIFY_DAILY_PROFILE", "Balanserad").strip() or "Balanserad"
RESEND_API_KEY = os.getenv("BORSIFY_RESEND_API_KEY", "").strip()
EMAIL_FROM = os.getenv("BORSIFY_EMAIL_FROM", "").strip()
APP_URL = os.getenv("BORSIFY_APP_URL", "https://borsify.se").strip() or "https://borsify.se"

if PROFILE not in core.PROFILE_WEIGHTS:
    PROFILE = "Balanserad"


def n(v, default=np.nan):
    try:
        x = float(v)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _send_resend_email(to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
    if not RESEND_API_KEY or not EMAIL_FROM:
        return False, "email_not_configured"
    payload = json.dumps({"from": EMAIL_FROM, "to": [to_email], "subject": subject, "html": html_body}).encode("utf-8")
    req = Request(
        "https://api.resend.com/emails",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Borsify/2.0.1",
        },
    )
    try:
        with urlopen(req, timeout=20) as response:
            ok = 200 <= int(getattr(response, "status", 0)) < 300
            return ok, "sent" if ok else f"http_{getattr(response, 'status', 'unknown')}"
    except HTTPError as exc:
        return False, f"http_{exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return False, type(exc).__name__


def _email_digest(signals: list[dict], today: str) -> str:
    items = []
    for sig in signals:
        icon = "🔔" if int(sig.get("priority") or 1) >= 3 else "⚠️"
        items.append(
            "<li style='margin:0 0 14px'>"
            f"<strong>{icon} {html.escape(str(sig.get('kind') or 'Signal'))} · {html.escape(str(sig.get('symbol') or ''))}</strong><br>"
            f"<span>{html.escape(str(sig.get('text') or ''))}</span>"
            "</li>"
        )
    return f"""
    <div style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#0f172a;line-height:1.45">
      <div style="background:#0f172a;color:white;padding:22px 24px;border-radius:14px 14px 0 0">
        <div style="font-size:24px;font-weight:800">Borsify Radar</div>
        <div style="color:#cbd5e1;margin-top:4px">{html.escape(today)} · {html.escape(PROFILE)}</div>
      </div>
      <div style="border:1px solid #e2e8f0;border-top:0;padding:22px 24px;border-radius:0 0 14px 14px">
        <p>Din automatiska scanning gav <strong>{len(signals)} signal{'er' if len(signals) != 1 else ''}</strong> som matchar dina e-postinställningar.</p>
        <ul style="padding-left:22px">{''.join(items)}</ul>
        <p><a href="{html.escape(APP_URL)}" style="display:inline-block;background:#0f172a;color:white;text-decoration:none;padding:10px 15px;border-radius:8px">Öppna Borsify</a></p>
        <p style="font-size:12px;color:#64748b">Borsify Score och signaler är kvantitativ screening och inte köp- eller säljråd. Kontrollera alltid bolagsdata och nyheter.</p>
      </div>
    </div>
    """


def _deliver_user_email(client, uid: str, today: str) -> bool:
    try:
        prefs_rows = (
            client.table("notification_preferences")
            .select("email_enabled,email,min_priority,notify_kinds")
            .eq("user_id", uid)
            .limit(1)
            .execute()
            .data
            or []
        )
    except Exception as exc:
        print(f"Email preferences unavailable: {type(exc).__name__}")
        return False
    if not prefs_rows:
        return False
    prefs = prefs_rows[0]
    if not bool(prefs.get("email_enabled")):
        return False
    to_email = str(prefs.get("email") or "").strip()
    if "@" not in to_email:
        return False
    min_priority = int(n(prefs.get("min_priority"), 2))
    allowed = prefs.get("notify_kinds")
    allowed_kinds = {str(x) for x in allowed} if isinstance(allowed, list) else set(core.SIGNAL_KINDS)

    rows = (
        client.table("signal_history")
        .select("event_key,symbol,kind,text,priority,email_sent_at")
        .eq("user_id", uid)
        .eq("profile", PROFILE)
        .eq("occurred_date", today)
        .execute()
        .data
        or []
    )
    pending = [
        r for r in rows
        if not r.get("email_sent_at")
        and int(n(r.get("priority"), 1)) >= min_priority
        and str(r.get("kind") or "") in allowed_kinds
    ]
    if not pending:
        return False

    pending.sort(key=lambda x: (-int(n(x.get("priority"), 1)), str(x.get("symbol") or ""), str(x.get("kind") or "")))
    subject = f"Borsify Radar: {len(pending)} signal{'er' if len(pending) != 1 else ''}"
    ok, reason = _send_resend_email(to_email, subject, _email_digest(pending, today))
    if not ok:
        print(f"Email delivery skipped/failed for one user: {reason}")
        return False

    sent_at = datetime.now(timezone.utc).isoformat()
    for sig in pending:
        client.table("signal_history").update({"email_sent_at": sent_at}).eq("user_id", uid).eq("event_key", str(sig["event_key"])).execute()
    print(f"Email digest sent with {len(pending)} signal(s).")
    return True


def main() -> int:
    if not URL or not KEY:
        raise SystemExit("Missing BORSIFY_SUPABASE_URL or BORSIFY_SUPABASE_SERVICE_ROLE_KEY")
    client = create_client(URL, KEY)
    watch = client.table("watchlist").select(
        "user_id,symbol,target_price,signal_score_threshold,signal_score_move,signal_daily_drop"
    ).execute().data or []
    if not watch:
        print("No watched shares; nothing to scan.")
        return 0

    universe = core.load_universe_file()["Ticker"].astype(str).tolist()
    raw, errors = core.scan_universe(universe)
    if raw.empty:
        raise SystemExit("No market data returned")
    scored = core.add_scores(raw, PROFILE)
    top = scored.head(20).reset_index(drop=True)
    today = datetime.now().date().isoformat()

    users = sorted({str(x["user_id"]) for x in watch})
    for uid in users:
        prev_dates = client.table("radar_history").select("captured_date").eq("user_id", uid).eq("profile", PROFILE).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
        prior_top = set()
        if prev_dates:
            d = prev_dates[0]["captured_date"]
            prior_top = {str(x["symbol"]) for x in (client.table("radar_history").select("symbol").eq("user_id", uid).eq("profile", PROFILE).eq("captured_date", d).lte("rank", 10).execute().data or [])}
        current_top = set(top.head(10)["Ticker"].astype(str))
        for i, row in top.iterrows():
            client.table("radar_history").upsert(
                {"user_id": uid, "symbol": str(row["Ticker"]), "profile": PROFILE, "rank": int(i + 1), "score": float(row["Borsify Score"]), "captured_date": today},
                on_conflict="user_id,symbol,profile,captured_date",
            ).execute()

        user_watch = [x for x in watch if str(x["user_id"]) == uid]
        by_symbol = {str(r["Ticker"]): r for _, r in scored.iterrows()}
        for meta in user_watch:
            sym = str(meta["symbol"])
            row = by_symbol.get(sym)
            if row is None:
                continue
            score = n(row.get("Borsify Score")); price = n(row.get("Pris")); daily = n(row.get("Dagsförändring"))
            prev_rows = client.table("score_history").select("score,captured_date").eq("user_id", uid).eq("symbol", sym).eq("profile", PROFILE).lt("captured_date", today).order("captured_date", desc=True).limit(1).execute().data or []
            prev = n(prev_rows[0]["score"]) if prev_rows else np.nan
            snapshot = {
                "user_id": uid, "symbol": sym, "score": float(score), "profile": PROFILE, "captured_date": today,
                "valuation": n(row.get("Värdering")), "quality": n(row.get("Kvalitet")), "setup": n(row.get("Marknadsläge")),
                "income": n(row.get("Utdelning")), "risk": n(row.get("Risk")), "coverage": n(row.get("Datatäckning")),
            }
            snapshot = {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in snapshot.items()}
            try:
                client.table("score_history").upsert(snapshot, on_conflict="user_id,symbol,profile,captured_date").execute()
            except Exception:
                # Allows the scanner to keep working until the v1.7 SQL migration has been run.
                fallback = {k: snapshot[k] for k in ["user_id", "symbol", "score", "profile", "captured_date"]}
                client.table("score_history").upsert(fallback, on_conflict="user_id,symbol,profile,captured_date").execute()
            move = n(meta.get("signal_score_move"), 8.0); threshold = n(meta.get("signal_score_threshold"), 75.0); drop = n(meta.get("signal_daily_drop"), 5.0); target = n(meta.get("target_price"))
            sigs: list[tuple[int, str, str]] = []
            if sym in current_top and prior_top and sym not in prior_top:
                rank = next((i + 1 for i, x in enumerate(top.head(10)["Ticker"].astype(str).tolist()) if x == sym), None)
                sigs.append((3, "Ny i topp 10", f"{sym} har gått in på plats {rank} i Borsify Radar ({score:.0f}/100)."))
            if np.isfinite(prev):
                delta = score - prev
                if delta >= move:
                    sigs.append((3, "Score lyfter", f"Borsify Score har stigit {delta:+.1f} till {score:.0f}/100. Din gräns är {move:.1f}."))
                if prev < threshold <= score:
                    sigs.append((2, "Scoregräns passerad", f"Borsify Score har passerat din gräns {threshold:.0f}: {prev:.1f} → {score:.1f}."))
                if delta <= -move:
                    sigs.append((2, "Score faller", f"Borsify Score har sjunkit {delta:.1f} till {score:.0f}/100. Din gräns är {move:.1f}."))
            if np.isfinite(target) and np.isfinite(price) and price >= target:
                sigs.append((3, "Målkurs nådd", f"Kursen {price:.2f} har nått/passerat din målkurs {target:.2f}."))
            if np.isfinite(daily) and daily <= -(drop / 100):
                sigs.append((2, "Kraftigt dagsfall", f"Aktien är ned {daily:.1%} idag, över din gräns på {drop:.1f} %."))
            for priority, kind, text in sigs:
                event_key = f"{today}|{PROFILE}|{sym}|{kind}"
                client.table("signal_history").upsert(
                    {"user_id": uid, "event_key": event_key, "symbol": sym, "kind": kind, "text": text, "priority": priority, "profile": PROFILE, "occurred_date": today},
                    on_conflict="user_id,event_key",
                ).execute()

        _deliver_user_email(client, uid, today)

    print(f"Scanned {len(scored)} shares for {len(users)} user(s). Errors: {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
