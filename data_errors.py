from __future__ import annotations
"""Classify external data failures into stable Borsify error categories."""

from typing import Any


def classify_data_error(exc: BaseException | None, *, context: str = "") -> dict[str, Any]:
    if exc is None:
        return {"type":"UnknownError","retryable":False,"context":context,"detail":""}

    name=type(exc).__name__
    text=str(exc or "")
    low=f"{name} {text}".lower()

    if isinstance(exc, TimeoutError) or any(x in low for x in ["timeout","timed out","readtimeout","connecttimeout"]):
        kind="Timeout"; retryable=True
    elif any(x in low for x in ["429","too many requests","rate limit","ratelimit","rate-limit"]):
        kind="RateLimited"; retryable=True
    elif isinstance(exc, (ConnectionError, OSError)) or any(x in low for x in ["connection reset","connection aborted","name resolution","dns","network is unreachable"]):
        kind="NetworkError"; retryable=True
    elif isinstance(exc, (KeyError, AttributeError, IndexError)) or any(x in low for x in ["schema","unexpected column","missing column","field not found"]):
        kind="SchemaChanged"; retryable=False
    elif isinstance(exc, (ValueError, TypeError)) or any(x in low for x in ["parse","decode","invalid json","jsondecode"]):
        kind="ParseError"; retryable=False
    elif any(x in low for x in ["no data","empty data","not found","404","delisted","possibly delisted"]):
        kind="NoData"; retryable=False
    else:
        kind="ProviderError"; retryable=False

    return {
        "type":kind,
        "retryable":retryable,
        "context":context,
        "detail":name,
    }


def classify_missing(*, context: str = "") -> dict[str, Any]:
    return {"type":"NoData","retryable":False,"context":context,"detail":""}


def format_error(err: dict[str, Any]) -> str:
    kind=str(err.get("type") or "UnknownError")
    context=str(err.get("context") or "")
    detail=str(err.get("detail") or "")
    suffix=" · ".join(x for x in [context,detail] if x)
    return f"{kind}: {suffix}" if suffix else kind
