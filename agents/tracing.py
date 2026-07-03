"""Optional Langfuse tracing — one trace per run, one span per graph node.

Design (mirrors AuditAgent's tracing.py):
  * **No-op by default.** With the LANGFUSE_* env vars unset (or the `langfuse`
    package absent), `get_tracer()` returns a tracer whose every method is a
    cheap no-op. Tests and zero-config runs are unaffected.
  * **Best-effort, never load-bearing.** Every real Langfuse call is wrapped so
    an SDK/network error degrades silently — the SSE stream + in-page trace stay
    the authoritative live view; Langfuse is the persistent observability record.
  * **SDK-version tolerant.** Langfuse v2 exposes `client.trace(...)` /
    `trace.span(...)`; v3 exposes `client.start_span(...)` context handles. We
    detect at runtime and adapt, so an unpinned `langfuse` dependency can't
    silently break tracing.

Enable by setting LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_HOST.
"""
from __future__ import annotations

import os
import time
from typing import Any

__all__ = ["get_tracer"]


# ── No-op implementation (the default) ─────────────────────────────────────

class _NoOpSpan:
    def update(self, **_kw: Any) -> None:
        pass

    def end(self, **_kw: Any) -> None:
        pass


class _NoOpRun:
    def span(self, _name: str, **_kw: Any) -> "_NoOpSpan":
        return _NoOpSpan()

    def update(self, **_kw: Any) -> None:
        pass

    def end(self, **_kw: Any) -> None:
        pass


class _NoOpTracer:
    enabled = False

    def start_run(self, _name: str, **_kw: Any) -> "_NoOpRun":
        return _NoOpRun()

    def flush(self) -> None:
        pass


# ── Live implementation (keys + SDK present) ───────────────────────────────

class _LiveSpan:
    def __init__(self, handle: Any, v3: bool) -> None:
        self._h = handle
        self._v3 = v3
        self._t0 = time.time()

    def update(self, **kw: Any) -> None:
        try:
            self._h.update(**kw)
        except Exception:  # noqa: BLE001 — tracing must never break a run
            pass

    def end(self, **kw: Any) -> None:
        try:
            if self._v3:
                if kw:
                    self._h.update(**kw)
                self._h.end()
            else:
                self._h.end(**kw)
        except Exception:  # noqa: BLE001
            pass


class _LiveRun:
    def __init__(self, client: Any, name: str, v3: bool, **kw: Any) -> None:
        self._client = client
        self._v3 = v3
        try:
            if v3:
                # v3: a root span is the trace container.
                self._h = client.start_span(name=name, metadata=kw or None)
                if kw.get("trace_id") is None and hasattr(self._h, "update_trace"):
                    self._h.update_trace(name=name, metadata=kw or None)
            else:
                self._h = client.trace(name=name, **kw)
        except Exception:  # noqa: BLE001
            self._h = None

    def span(self, name: str, **kw: Any) -> _LiveSpan | _NoOpSpan:
        if self._h is None:
            return _NoOpSpan()
        try:
            if self._v3:
                return _LiveSpan(self._h.start_span(name=name, metadata=kw or None), True)
            return _LiveSpan(self._h.span(name=name, **kw), False)
        except Exception:  # noqa: BLE001
            return _NoOpSpan()

    def update(self, **kw: Any) -> None:
        if self._h is None:
            return
        try:
            if self._v3 and hasattr(self._h, "update_trace"):
                self._h.update_trace(**kw)
            else:
                self._h.update(**kw)
        except Exception:  # noqa: BLE001
            pass

    def end(self, **kw: Any) -> None:
        if self._h is None:
            return
        try:
            if self._v3:
                if kw:
                    self._h.update(**kw)
                self._h.end()
            else:
                self._h.update(**kw)
        except Exception:  # noqa: BLE001
            pass


class _LiveTracer:
    enabled = True

    def __init__(self, client: Any, v3: bool) -> None:
        self._client = client
        self._v3 = v3

    def start_run(self, name: str, **kw: Any) -> _LiveRun:
        return _LiveRun(self._client, name, self._v3, **kw)

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception:  # noqa: BLE001
            pass


_TRACER: Any = None


def get_tracer() -> Any:
    """Langfuse-backed tracer when configured, else a zero-cost no-op."""
    global _TRACER
    if _TRACER is not None:
        return _TRACER
    if not (os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")):
        _TRACER = _NoOpTracer()
        return _TRACER
    try:
        from langfuse import Langfuse  # optional dep

        client = Langfuse()  # reads LANGFUSE_* env vars
        v3 = not hasattr(client, "trace")  # v2 has .trace; v3 has .start_span
        _TRACER = _LiveTracer(client, v3)
    except Exception:  # noqa: BLE001 — missing/broken SDK → no-op
        _TRACER = _NoOpTracer()
    return _TRACER
