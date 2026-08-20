"""Structured observability: JSON logging, call instrumentation, and PII redaction.

`instrument` wraps `agent/tools/*` functions -- the boundary this project actually
controls. Agent Engine's managed runtime drives the ADK `Runner` internally, so a
decorator on `Runner.run_async` would never fire in production; tool calls are invoked
by our own code regardless of where the agent runs, so that's the choke point used here.

Cloud Logging parses a JSON-formatted stdout line into `jsonPayload` automatically, and
promotes reserved top-level keys -- `severity` here -- out of `jsonPayload` into the
LogEntry's own fields, making them filterable in Logs Explorer (e.g. `severity=ERROR`).
No separate log sink is needed: Agent Engine forwards container stdout/stderr to Cloud
Logging on its own, the same way Cloud Run does.
"""

from __future__ import annotations

import functools
import inspect
import json
import logging
import re
import sys
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger("{{cookiecutter.project_slug}}.observability")
if not logger.handlers:
    _handler = logging.StreamHandler(sys.stdout)
    _handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False

F = TypeVar("F", bound=Callable[..., Any])

# Best-effort patterns for common PII shapes. Not exhaustive -- a defence in depth
# measure for logs, not a substitute for not logging sensitive fields in the first place.
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"), "[REDACTED_EMAIL]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
    (re.compile(r"\b(?:\d{4}[ -]?){3}\d{4}\b"), "[REDACTED_CARD]"),
]


def redact_pii(value: Any) -> Any:
    """Redact emails, SSNs, and credit-card-shaped numbers from a value.

    Recurses into dicts, lists, and tuples; strings are scanned in place; any
    other type passes through unchanged.
    """
    if isinstance(value, str):
        redacted = value
        for pattern, placeholder in _PII_PATTERNS:
            redacted = pattern.sub(placeholder, redacted)
        return redacted
    if isinstance(value, dict):
        return {key: redact_pii(val) for key, val in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_pii(item) for item in value]
    return value


def log_event(
    event_type: str, fields: dict[str, Any] | None = None, severity: str = "INFO"
) -> None:
    """Emit one structured JSON log line for Cloud Logging.

    `severity` is a Cloud Logging reserved field (`INFO`, `ERROR`, ...), promoted out
    of `jsonPayload` into the LogEntry itself. `agent_name` matches the filter already
    used by `deployment/scripts/read_logs.sh`. All other field values are passed
    through `redact_pii` first.
    """
    payload: dict[str, Any] = {
        "severity": severity,
        "agent_name": "root_agent",
        "event": event_type,
    }
    payload.update(redact_pii(fields or {}))
    log = logger.error if severity == "ERROR" else logger.info
    log(json.dumps(payload, default=str))


def log_model_usage(event: Any) -> None:
    """Log token counts from an ADK event's `usage_metadata`, if present.

    Only reachable in code that iterates the event stream itself (e.g. the
    promptfoo eval provider) -- Agent Engine's own request path never runs
    this, since its managed runtime drives the Runner internally.
    """
    try:
        usage = getattr(event, "usage_metadata", None)
        if usage is None:
            return
        log_event(
            "model.usage",
            {
                "prompt_tokens": getattr(usage, "prompt_token_count", None),
                "candidates_tokens": getattr(usage, "candidates_token_count", None),
                "total_tokens": getattr(usage, "total_token_count", None),
            },
        )
    except Exception:
        logger.debug("Could not extract usage metadata from event", exc_info=True)


def instrument(func: F) -> F:
    """Log name, (redacted) arguments, outcome, and duration for every call.

    Works on sync or async callables. `functools.wraps` keeps the wrapped
    function's name, docstring, and signature intact via `__wrapped__`, so
    ADK's tool-schema introspection sees the original function unchanged.
    """

    def _start(args: tuple[Any, ...], kwargs: dict[str, Any]) -> float:
        log_event(f"{func.__name__}.start", {"args": args, "kwargs": kwargs})
        return time.perf_counter()

    def _end(start: float) -> None:
        duration_ms = (time.perf_counter() - start) * 1000
        log_event(
            f"{func.__name__}.end",
            {"duration_ms": round(duration_ms, 2), "outcome": "success"},
        )

    def _error(start: float, exc: Exception) -> None:
        duration_ms = (time.perf_counter() - start) * 1000
        log_event(
            f"{func.__name__}.error",
            {"duration_ms": round(duration_ms, 2), "error": str(exc)},
            severity="ERROR",
        )

    if inspect.iscoroutinefunction(func):

        @functools.wraps(func)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = _start(args, kwargs)
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                _error(start, exc)
                raise
            _end(start)
            return result

        return _async_wrapper  # type: ignore[return-value]

    @functools.wraps(func)
    def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
        start = _start(args, kwargs)
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            _error(start, exc)
            raise
        _end(start)
        return result

    return _sync_wrapper  # type: ignore[return-value]
