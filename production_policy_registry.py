from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REGISTRY_VERSION = "1"
EVENT_ACTIVATION = "ACTIVATION"
EVENT_PROMOTION = "PROMOTION"
EVENT_ROLLBACK = "ROLLBACK"

DEFAULT_POLICY_ID = "selection-policy-baseline-v1"
DEFAULT_POLICY_LABEL = "Nuvarande urvalspolicy · baseline"

# The active policy contract is deliberately explicit and small. A future release
# that truly deploys one of the pre-registered policies must update this contract
# to that exact registered definition. Merely recording a promotion event does not
# silently change production behavior.
ACTIVE_POLICY_CONTRACT: dict[str, str] = {
    "policy_id": DEFAULT_POLICY_ID,
    "name": DEFAULT_POLICY_LABEL,
    "thesis": "Behåll nuvarande urvalsregler utan de nya förregistrerade extra regimkraven.",
    "target_definition": "Nuvarande produktionsurval och kvalitetsgrindar enligt releasekod.",
    "requirement_definition": "Ingen av v3.15-hypotesernas extra krav är aktiverad i produktion.",
    "registered_model_version": "3.18.0",
    "registered_date": "2026-09-06",
    "registry_version": REGISTRY_VERSION,
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def policy_contract_fingerprint(contract: dict[str, Any]) -> str:
    raw = json.dumps(contract, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def active_policy_fingerprint() -> str:
    return policy_contract_fingerprint(ACTIVE_POLICY_CONTRACT)


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_policy_registry(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS production_policy_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                effective_at TEXT NOT NULL,
                registry_version TEXT NOT NULL,
                app_version TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                policy_label TEXT NOT NULL,
                policy_fingerprint TEXT NOT NULL,
                previous_policy_id TEXT,
                previous_fingerprint TEXT,
                candidate_policy_id TEXT,
                candidate_fingerprint TEXT,
                source_event_id TEXT,
                decision_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                rollback_trigger TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_production_policy_events_time ON production_policy_events(effective_at, event_id)"
        )
        conn.commit()


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    result = dict(row)
    try:
        result["metadata"] = json.loads(result.pop("metadata_json", "{}") or "{}")
    except Exception:
        result["metadata"] = {}
        result.pop("metadata_json", None)
    return result


def current_policy(db_path: str | Path) -> dict[str, Any] | None:
    ensure_policy_registry(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM production_policy_events ORDER BY effective_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return _row_to_dict(row)


def bootstrap_policy_registry(db_path: str | Path, app_version: str) -> dict[str, Any]:
    """Register the currently deployed policy contract once, without changing it."""
    ensure_policy_registry(db_path)
    existing = current_policy(db_path)
    if existing is not None:
        return existing
    event_id = f"activation-{uuid.uuid4().hex}"
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO production_policy_events (
                event_id,event_type,effective_at,registry_version,app_version,
                policy_id,policy_label,policy_fingerprint,decision_by,reason,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_ACTIVATION, _utc_now(), REGISTRY_VERSION, str(app_version),
                ACTIVE_POLICY_CONTRACT["policy_id"], ACTIVE_POLICY_CONTRACT["name"], active_policy_fingerprint(),
                "system-bootstrap",
                "Initial aktiv urvalspolicy registrerad för spårbarhet. Ingen policyändring utfördes.",
                json.dumps({"active_policy_contract": ACTIVE_POLICY_CONTRACT}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_policy(db_path) or {}


def _require_manual(manual_decision: bool, reason: str, decision_by: str) -> None:
    if manual_decision is not True:
        raise ValueError("Policy-promotion/rollback kräver ett uttryckligt manuellt beslut.")
    if not str(reason or "").strip():
        raise ValueError("Beslutsmotivering måste dokumenteras.")
    if not str(decision_by or "").strip():
        raise ValueError("Beslutsfattare måste dokumenteras.")


def record_policy_promotion(
    db_path: str | Path,
    *,
    app_version: str,
    candidate_policy_id: str,
    candidate_label: str,
    candidate_fingerprint: str,
    promotion_status: str,
    expected_ready_status: str,
    reason: str,
    decision_by: str,
    rollback_trigger: str,
    manual_decision: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a manually approved policy promotion decision.

    This is governance state only. The runtime contract must still be updated in a
    release; until then registry_summary intentionally reports a runtime mismatch.
    """
    _require_manual(manual_decision, reason, decision_by)
    if str(promotion_status) != str(expected_ready_status):
        raise ValueError("Policyn har inte status redo för manuell policy-promotion.")
    if not str(candidate_policy_id or "").strip() or not str(candidate_fingerprint or "").strip():
        raise ValueError("Policy-ID och fingerprint krävs.")
    if not str(rollback_trigger or "").strip():
        raise ValueError("Rollback-trigger måste dokumenteras före promotion.")
    previous = current_policy(db_path)
    if previous is None:
        raise ValueError("Policyregistret måste bootstrapas innan promotion.")
    if previous.get("policy_fingerprint") == str(candidate_fingerprint):
        raise ValueError("Kandidatpolicyn är identisk med nuvarande policydefinition.")

    payload = dict(metadata or {})
    payload["promoted_from_event"] = previous.get("event_id")
    payload["deployment_required"] = True
    event_id = f"promotion-{uuid.uuid4().hex}"
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO production_policy_events (
                event_id,event_type,effective_at,registry_version,app_version,
                policy_id,policy_label,policy_fingerprint,previous_policy_id,previous_fingerprint,
                candidate_policy_id,candidate_fingerprint,source_event_id,decision_by,reason,
                rollback_trigger,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_PROMOTION, _utc_now(), REGISTRY_VERSION, str(app_version),
                str(candidate_policy_id), str(candidate_label), str(candidate_fingerprint),
                previous.get("policy_id"), previous.get("policy_fingerprint"),
                str(candidate_policy_id), str(candidate_fingerprint), previous.get("event_id"),
                str(decision_by).strip(), str(reason).strip(), str(rollback_trigger).strip(),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_policy(db_path) or {}


def record_policy_rollback(
    db_path: str | Path,
    *,
    app_version: str,
    reason: str,
    decision_by: str,
    manual_decision: bool = False,
    target_event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a rollback to a previously registered policy definition."""
    _require_manual(manual_decision, reason, decision_by)
    current = current_policy(db_path)
    if current is None:
        raise ValueError("Policyregistret är tomt.")
    ensure_policy_registry(db_path)
    with _connect(db_path) as conn:
        if target_event_id:
            target = conn.execute(
                "SELECT * FROM production_policy_events WHERE event_id = ?", (str(target_event_id),)
            ).fetchone()
        else:
            prev_id = current.get("previous_policy_id")
            prev_fp = current.get("previous_fingerprint")
            target = conn.execute(
                """
                SELECT * FROM production_policy_events
                WHERE policy_id = ? AND policy_fingerprint = ?
                ORDER BY effective_at DESC, rowid DESC LIMIT 1
                """,
                (prev_id, prev_fp),
            ).fetchone() if prev_id and prev_fp else None
        target_dict = _row_to_dict(target)
        if not target_dict:
            raise ValueError("Ingen tidigare policydefinition kunde hittas för rollback.")
        if target_dict.get("policy_fingerprint") == current.get("policy_fingerprint"):
            raise ValueError("Rollback-målet är samma definition som nuvarande policy.")

        event_id = f"rollback-{uuid.uuid4().hex}"
        payload = dict(metadata or {})
        payload["rolled_back_from_event"] = current.get("event_id")
        payload["target_event_id"] = target_dict.get("event_id")
        conn.execute(
            """
            INSERT INTO production_policy_events (
                event_id,event_type,effective_at,registry_version,app_version,
                policy_id,policy_label,policy_fingerprint,previous_policy_id,previous_fingerprint,
                source_event_id,decision_by,reason,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_ROLLBACK, _utc_now(), REGISTRY_VERSION, str(app_version),
                target_dict.get("policy_id"), target_dict.get("policy_label"), target_dict.get("policy_fingerprint"),
                current.get("policy_id"), current.get("policy_fingerprint"), current.get("event_id"),
                str(decision_by).strip(), str(reason).strip(),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_policy(db_path) or {}


def policy_registry_history(db_path: str | Path) -> pd.DataFrame:
    ensure_policy_registry(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM production_policy_events ORDER BY effective_at DESC, rowid DESC"
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    data: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        data.append({
            "Tid": item.get("effective_at"),
            "Händelse": item.get("event_type"),
            "Aktiv policy": item.get("policy_label"),
            "Policy ID": item.get("policy_id"),
            "Fingerprint": item.get("policy_fingerprint"),
            "Appversion": item.get("app_version"),
            "Föregående": item.get("previous_policy_id") or "—",
            "Beslut av": item.get("decision_by"),
            "Motivering": item.get("reason"),
            "Rollback-trigger": item.get("rollback_trigger") or "—",
            "Event ID": item.get("event_id"),
        })
    return pd.DataFrame(data)


def policy_registry_summary(db_path: str | Path, app_version: str) -> dict[str, Any]:
    current = bootstrap_policy_registry(db_path, app_version)
    runtime_fp = active_policy_fingerprint()
    registered_fp = str(current.get("policy_fingerprint") or "")
    matches = bool(registered_fp) and registered_fp == runtime_fp
    return {
        "policy": current.get("policy_label") or "Okänd policy",
        "policy_id": current.get("policy_id") or "—",
        "registered_fingerprint": registered_fp or "—",
        "runtime_fingerprint": runtime_fp,
        "definition_matches_runtime": matches,
        "status": "Matchar registrerad policy" if matches else "Policybeslut och runtime avviker – granska release",
        "event_id": current.get("event_id") or "—",
        "note": (
            "Registret är append-only och ändrar aldrig urvalsregler automatiskt. "
            "En promotion måste följas av en explicit release som uppdaterar ACTIVE_POLICY_CONTRACT till exakt den registrerade definitionen. "
            "SQLite-historik kräver beständig lagring för att överleva omdeploy/restart."
        ),
    }
