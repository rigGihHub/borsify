from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd


def _connect(path: str | Path) -> sqlite3.Connection:
    conn=sqlite3.connect(str(path),timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS prefilter_validation (
            validation_date TEXT NOT NULL,
            market TEXT NOT NULL,
            universe_size INTEGER NOT NULL,
            pool_size INTEGER NOT NULL,
            target_count INTEGER NOT NULL,
            retained_count INTEGER NOT NULL,
            retention REAL,
            pool_fraction REAL,
            missed_symbols TEXT,
            model_version TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY(validation_date,market,model_version)
        )
        """
    )
    return conn


def save_prefilter_validation(
    db_path: str | Path,
    market: str,
    result: dict[str,Any],
    model_version: str,
    validation_date: str | None=None,
) -> None:
    date=validation_date or datetime.now().date().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO prefilter_validation(
                validation_date,market,universe_size,pool_size,target_count,
                retained_count,retention,pool_fraction,missed_symbols,
                model_version,created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(validation_date,market,model_version) DO UPDATE SET
                universe_size=excluded.universe_size,
                pool_size=excluded.pool_size,
                target_count=excluded.target_count,
                retained_count=excluded.retained_count,
                retention=excluded.retention,
                pool_fraction=excluded.pool_fraction,
                missed_symbols=excluded.missed_symbols,
                created_at=excluded.created_at
            """,
            (
                date,str(market),int(result.get("universe",0)),int(result.get("pool",0)),
                int(result.get("targets",0)),int(result.get("retained",0)),
                result.get("retention"),result.get("fraction"),
                ",".join(map(str,result.get("missed",[]) or [])),
                str(model_version),datetime.now().isoformat(timespec="seconds"),
            ),
        )


def get_prefilter_validation_history(
    db_path: str | Path,
    market: str | None=None,
    limit: int=50,
) -> pd.DataFrame:
    with _connect(db_path) as conn:
        if market:
            rows=conn.execute(
                """
                SELECT * FROM prefilter_validation
                WHERE market=?
                ORDER BY validation_date DESC, created_at DESC
                LIMIT ?
                """,
                (str(market),int(limit)),
            ).fetchall()
        else:
            rows=conn.execute(
                """
                SELECT * FROM prefilter_validation
                ORDER BY validation_date DESC, created_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        cols=[d[0] for d in conn.execute("SELECT * FROM prefilter_validation LIMIT 0").description]
    return pd.DataFrame(rows,columns=cols)
