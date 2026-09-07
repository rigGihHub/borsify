from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

REGISTRY_VERSION = "1"
DEFAULT_CHAMPION_ID = "short-alpha-champion-v1"
DEFAULT_CHAMPION_LABEL = "Short Alpha · nuvarande champion"
DEFAULT_LINEAGE = "Produktionslogik införd t.o.m. v3.03.0; modellstyrning därefter ändrar inte champion automatiskt."
EVENT_ACTIVATION = "ACTIVATION"
EVENT_PROMOTION = "PROMOTION"
EVENT_ROLLBACK = "ROLLBACK"

# Files that materially define the current Short Alpha / decision support model.
# Hashing their contents gives a reproducible fingerprint without pretending that
# an app release number alone identifies the exact model definition.
MODEL_SOURCE_FILES = (
    "short_term_engine.py",
    "signal_ablation.py",
    "case_quality_gate.py",
    "evidence_families.py",
    "post_report_drift.py",
    "earnings_quality.py",
    "investment_discipline.py",
    "momentum_12_1.py",
    "idiosyncratic_volatility.py",
    "expectation_change.py",
    "sector_valuation.py",
)


@dataclass(frozen=True)
class ProductionModel:
    model_id: str
    label: str
    fingerprint: str
    app_version: str
    lineage: str = DEFAULT_LINEAGE


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def production_definition_fingerprint(base_dir: str | Path | None = None) -> str:
    """Hash the exact model-relevant source files in a stable order.

    Missing files are included as explicit markers, so a partial package cannot
    accidentally receive the same fingerprint as a complete model definition.
    """
    root = Path(base_dir) if base_dir is not None else Path(__file__).resolve().parent
    digest = hashlib.sha256()
    digest.update(f"registry={REGISTRY_VERSION}\n".encode("utf-8"))
    for name in MODEL_SOURCE_FILES:
        path = root / name
        digest.update(f"FILE:{name}\n".encode("utf-8"))
        if path.exists() and path.is_file():
            digest.update(path.read_bytes())
        else:
            digest.update(b"<MISSING>")
        digest.update(b"\n")
    return digest.hexdigest()[:20]


def default_champion(app_version: str, base_dir: str | Path | None = None) -> ProductionModel:
    return ProductionModel(
        model_id=DEFAULT_CHAMPION_ID,
        label=DEFAULT_CHAMPION_LABEL,
        fingerprint=production_definition_fingerprint(base_dir),
        app_version=str(app_version),
    )


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_registry(db_path: str | Path) -> None:
    with _connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS production_model_events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                effective_at TEXT NOT NULL,
                registry_version TEXT NOT NULL,
                app_version TEXT NOT NULL,
                model_id TEXT NOT NULL,
                model_label TEXT NOT NULL,
                model_fingerprint TEXT NOT NULL,
                previous_model_id TEXT,
                previous_fingerprint TEXT,
                challenger_id TEXT,
                challenger_fingerprint TEXT,
                source_event_id TEXT,
                decision_by TEXT NOT NULL,
                reason TEXT NOT NULL,
                rollback_trigger TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_production_model_events_time ON production_model_events(effective_at, event_id)"
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


def current_champion(db_path: str | Path) -> dict[str, Any] | None:
    ensure_registry(db_path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM production_model_events ORDER BY effective_at DESC, rowid DESC LIMIT 1"
        ).fetchone()
    return _row_to_dict(row)


def bootstrap_registry(
    db_path: str | Path,
    app_version: str,
    base_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Create one immutable baseline activation if the registry is empty.

    This documents the champion; it does not alter model code or weights.
    """
    ensure_registry(db_path)
    existing = current_champion(db_path)
    if existing is not None:
        return existing
    champion = default_champion(app_version, base_dir)
    event_id = f"activation-{uuid.uuid4().hex}"
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO production_model_events (
                event_id,event_type,effective_at,registry_version,app_version,
                model_id,model_label,model_fingerprint,decision_by,reason,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_ACTIVATION, _utc_now(), REGISTRY_VERSION, champion.app_version,
                champion.model_id, champion.label, champion.fingerprint,
                "system-bootstrap",
                "Initial champion registrerad för spårbarhet. Ingen modelländring utfördes.",
                json.dumps({"lineage": champion.lineage, "source_files": list(MODEL_SOURCE_FILES)}, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_champion(db_path) or {}


def _require_manual_decision(manual_decision: bool, reason: str, decision_by: str) -> None:
    if manual_decision is not True:
        raise ValueError("Promotion/rollback kräver ett uttryckligt manuellt beslut.")
    if not str(reason or "").strip():
        raise ValueError("Beslutsmotivering måste dokumenteras.")
    if not str(decision_by or "").strip():
        raise ValueError("Beslutsfattare måste dokumenteras.")


def record_promotion(
    db_path: str | Path,
    *,
    app_version: str,
    challenger_id: str,
    challenger_label: str,
    challenger_fingerprint: str,
    promotion_status: str,
    expected_ready_status: str,
    reason: str,
    decision_by: str,
    rollback_trigger: str,
    manual_decision: bool = False,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a promotion event after the external promotion protocol has passed.

    The function records governance state only. It never rewrites model weights,
    source code, or challenger definitions.
    """
    _require_manual_decision(manual_decision, reason, decision_by)
    if str(promotion_status) != str(expected_ready_status):
        raise ValueError("Challengern har inte status redo för manuell promotionsprövning.")
    if not str(challenger_fingerprint or "").strip():
        raise ValueError("Challenger-fingerprint saknas.")
    if not str(rollback_trigger or "").strip():
        raise ValueError("Rollback-trigger måste dokumenteras före promotion.")
    previous = current_champion(db_path)
    if previous is None:
        raise ValueError("Produktionsregistret måste bootstrapas innan promotion.")
    if previous.get("model_fingerprint") == challenger_fingerprint:
        raise ValueError("Challenger-definitionen är identisk med nuvarande champion.")

    event_id = f"promotion-{uuid.uuid4().hex}"
    payload = dict(metadata or {})
    payload["promoted_from_event"] = previous.get("event_id")
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO production_model_events (
                event_id,event_type,effective_at,registry_version,app_version,
                model_id,model_label,model_fingerprint,previous_model_id,previous_fingerprint,
                challenger_id,challenger_fingerprint,source_event_id,decision_by,reason,
                rollback_trigger,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_PROMOTION, _utc_now(), REGISTRY_VERSION, str(app_version),
                str(challenger_id), str(challenger_label), str(challenger_fingerprint),
                previous.get("model_id"), previous.get("model_fingerprint"),
                str(challenger_id), str(challenger_fingerprint), previous.get("event_id"),
                str(decision_by).strip(), str(reason).strip(), str(rollback_trigger).strip(),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_champion(db_path) or {}


def record_rollback(
    db_path: str | Path,
    *,
    app_version: str,
    reason: str,
    decision_by: str,
    manual_decision: bool = False,
    target_event_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a rollback to a previously known champion definition.

    Default target is the model that immediately preceded the current promotion.
    Rollback does not modify source code; deployment/release remains a separate,
    explicit operational step.
    """
    _require_manual_decision(manual_decision, reason, decision_by)
    current = current_champion(db_path)
    if current is None:
        raise ValueError("Produktionsregistret är tomt.")
    ensure_registry(db_path)
    with _connect(db_path) as conn:
        if target_event_id:
            target = conn.execute("SELECT * FROM production_model_events WHERE event_id = ?", (str(target_event_id),)).fetchone()
        else:
            prev_id = current.get("previous_model_id")
            prev_fp = current.get("previous_fingerprint")
            target = conn.execute(
                """
                SELECT * FROM production_model_events
                WHERE model_id = ? AND model_fingerprint = ?
                ORDER BY effective_at DESC, rowid DESC LIMIT 1
                """,
                (prev_id, prev_fp),
            ).fetchone() if prev_id and prev_fp else None
        target_dict = _row_to_dict(target)
        if not target_dict:
            raise ValueError("Ingen tidigare champion-definition kunde hittas för rollback.")
        if target_dict.get("model_fingerprint") == current.get("model_fingerprint"):
            raise ValueError("Rollback-målet är samma definition som nuvarande champion.")
        event_id = f"rollback-{uuid.uuid4().hex}"
        payload = dict(metadata or {})
        payload["rolled_back_from_event"] = current.get("event_id")
        payload["target_event_id"] = target_dict.get("event_id")
        conn.execute(
            """
            INSERT INTO production_model_events (
                event_id,event_type,effective_at,registry_version,app_version,
                model_id,model_label,model_fingerprint,previous_model_id,previous_fingerprint,
                source_event_id,decision_by,reason,metadata_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                event_id, EVENT_ROLLBACK, _utc_now(), REGISTRY_VERSION, str(app_version),
                target_dict.get("model_id"), target_dict.get("model_label"), target_dict.get("model_fingerprint"),
                current.get("model_id"), current.get("model_fingerprint"), current.get("event_id"),
                str(decision_by).strip(), str(reason).strip(),
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
            ),
        )
        conn.commit()
    return current_champion(db_path) or {}


def registry_history(db_path: str | Path) -> pd.DataFrame:
    ensure_registry(db_path)
    with _connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM production_model_events ORDER BY effective_at DESC, rowid DESC"
        ).fetchall()
    if not rows:
        return pd.DataFrame()
    data = []
    for row in rows:
        item = dict(row)
        data.append({
            "Tid": item.get("effective_at"),
            "Händelse": item.get("event_type"),
            "Champion": item.get("model_label"),
            "Model ID": item.get("model_id"),
            "Fingerprint": item.get("model_fingerprint"),
            "Appversion": item.get("app_version"),
            "Föregående": item.get("previous_model_id") or "—",
            "Beslut av": item.get("decision_by"),
            "Motivering": item.get("reason"),
            "Rollback-trigger": item.get("rollback_trigger") or "—",
            "Event ID": item.get("event_id"),
        })
    return pd.DataFrame(data)


def registry_summary(db_path: str | Path, app_version: str, base_dir: str | Path | None = None) -> dict[str, Any]:
    current = bootstrap_registry(db_path, app_version, base_dir)
    live_fingerprint = production_definition_fingerprint(base_dir)
    registered = str(current.get("model_fingerprint") or "")
    matches = bool(registered) and registered == live_fingerprint
    return {
        "champion": current.get("model_label") or "Okänd champion",
        "model_id": current.get("model_id") or "—",
        "registered_fingerprint": registered or "—",
        "live_fingerprint": live_fingerprint,
        "definition_matches_runtime": matches,
        "status": "Matchar registrerad champion" if matches else "Definition avviker – granska före promotion",
        "event_id": current.get("event_id") or "—",
        "note": (
            "Registret dokumenterar beslut och definitioner; det ändrar aldrig modellkod automatiskt. "
            "SQLite-filen måste ligga på beständig lagring för att historiken ska överleva omdeploy/restart."
        ),
    }
