from __future__ import annotations
"""Retry and circuit-breaker utilities for external Borsify data providers.

Only retryable classified failures are retried. Circuit state is process-local and
advisory: it protects the app from repeatedly hammering a failing provider during one
runtime session without pretending that a provider is permanently unavailable.
"""

from dataclasses import dataclass
from threading import Lock
from time import monotonic, sleep
from typing import Any, Callable

from data_errors import classify_data_error


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float | None = None
    last_error_type: str = ""


_LOCK = Lock()
_CIRCUITS: dict[str, CircuitState] = {}


def reset_circuit(key: str | None = None) -> None:
    with _LOCK:
        if key is None:
            _CIRCUITS.clear()
        else:
            _CIRCUITS.pop(key, None)


def circuit_snapshot(key: str) -> dict[str, Any]:
    with _LOCK:
        s=_CIRCUITS.get(key, CircuitState())
        return {
            "failures":s.failures,
            "opened_at":s.opened_at,
            "last_error_type":s.last_error_type,
        }


def _state(key: str) -> CircuitState:
    with _LOCK:
        return _CIRCUITS.setdefault(key, CircuitState())


def is_circuit_open(key: str, *, cooldown_seconds: float = 60.0) -> bool:
    with _LOCK:
        s=_CIRCUITS.get(key)
        if s is None or s.opened_at is None:
            return False
        if monotonic() - s.opened_at >= cooldown_seconds:
            # Half-open: allow one new request by resetting accumulated failures.
            s.failures=0
            s.opened_at=None
            s.last_error_type=""
            return False
        return True


def record_success(key: str) -> None:
    with _LOCK:
        _CIRCUITS[key]=CircuitState()


def record_failure(key: str, error_type: str, *, threshold: int = 3) -> None:
    with _LOCK:
        s=_CIRCUITS.setdefault(key,CircuitState())
        s.failures += 1
        s.last_error_type=error_type
        if s.failures >= threshold and s.opened_at is None:
            s.opened_at=monotonic()


class CircuitOpenError(RuntimeError):
    pass


def call_with_resilience(
    func: Callable[[], Any],
    *,
    provider_key: str,
    context: str,
    max_attempts: int = 2,
    base_delay_seconds: float = 0.15,
    circuit_threshold: int = 3,
    cooldown_seconds: float = 60.0,
    sleep_fn: Callable[[float], None] = sleep,
) -> tuple[Any, dict[str, Any]]:
    """Execute an external call with classified retry and circuit protection.

    Non-retryable failures are returned after one attempt. Retryable failures may be
    retried up to max_attempts. A provider circuit opens only after consecutive failures.
    """
    if is_circuit_open(provider_key,cooldown_seconds=cooldown_seconds):
        snap=circuit_snapshot(provider_key)
        err={
            "type":"CircuitOpen",
            "retryable":True,
            "context":context,
            "detail":snap.get("last_error_type") or "",
        }
        return None,{
            "ok":False,
            "attempts":0,
            "error":err,
            "circuit_open":True,
            "provider_key":provider_key,
        }

    attempts=0
    last_err=None
    while attempts < max(1,int(max_attempts)):
        attempts += 1
        try:
            value=func()
            record_success(provider_key)
            return value,{
                "ok":True,
                "attempts":attempts,
                "error":None,
                "circuit_open":False,
                "provider_key":provider_key,
            }
        except Exception as exc:
            err=classify_data_error(exc,context=context)
            last_err=err
            record_failure(provider_key,err["type"],threshold=circuit_threshold)
            if not err.get("retryable") or attempts >= max_attempts:
                break
            delay=max(0.0,float(base_delay_seconds))*(2 ** (attempts-1))
            if delay:
                sleep_fn(delay)

    return None,{
        "ok":False,
        "attempts":attempts,
        "error":last_err,
        "circuit_open":is_circuit_open(provider_key,cooldown_seconds=cooldown_seconds),
        "provider_key":provider_key,
    }
