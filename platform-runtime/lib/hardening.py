"""MSN-0061 Workstream B — Slack Commander Tier-1 hardening primitives.

Stdlib-only by design: importing this module must never be able to block bot
startup, so it pulls in no third-party packages. Every primitive is testable
in isolation without a live Slack/Supabase connection.

Provides:
  - ``slog`` / ``slog_*``      structured, greppable key=value log lines
  - ``classify_auth_error``    map an exception to a Slack/Supabase auth code
  - ``verify_slack_auth``      startup auth.test that fails loudly, not silently
  - ``WorkerRegistry``         track in-flight background workers; drain on exit
  - ``GracefulShutdown``       SIGTERM/SIGINT coordinator running ordered hooks
  - ``Metrics`` + ``start_metrics_server``  optional Prometheus text endpoint
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from typing import Callable, Dict, Iterable, Optional, Tuple

__all__ = [
    "slog",
    "slog_info",
    "slog_warning",
    "slog_error",
    "AuthError",
    "AUTH_ERROR_CODES",
    "classify_auth_error",
    "verify_slack_auth",
    "WorkerRegistry",
    "GracefulShutdown",
    "Metrics",
    "start_metrics_server",
]

_DEFAULT_LOGGER = logging.getLogger("commander.hardening")

# Cap individual field values so a stray giant string can't blow up a log line.
_MAX_FIELD_LEN = 300


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
def _render_field(value: object) -> str:
    """Render one field value as a compact, single-token-ish string."""
    text = str(value)
    if len(text) > _MAX_FIELD_LEN:
        text = text[: _MAX_FIELD_LEN - 1] + "…"
    # Quote anything containing whitespace or our delimiter so the line stays
    # parseable as space-separated key=value pairs.
    if text == "" or any(ch.isspace() for ch in text) or "=" in text:
        text = '"' + text.replace('"', "'") + '"'
    return text


def slog(logger: logging.Logger, event: str, level: int = logging.INFO, **fields: object) -> None:
    """Emit one structured ``event=… key=value …`` line.

    Keeps a single, greppable shape across the known failure modes so operators
    can diagnose from logs without reading code.
    """
    parts = ["event=" + _render_field(event)]
    for key, value in fields.items():
        parts.append(f"{key}=" + _render_field(value))
    (logger or _DEFAULT_LOGGER).log(level, "[commander] " + " ".join(parts))


def slog_info(logger: logging.Logger, event: str, **fields: object) -> None:
    slog(logger, event, level=logging.INFO, **fields)


def slog_warning(logger: logging.Logger, event: str, **fields: object) -> None:
    slog(logger, event, level=logging.WARNING, **fields)


def slog_error(logger: logging.Logger, event: str, **fields: object) -> None:
    slog(logger, event, level=logging.ERROR, **fields)


# ---------------------------------------------------------------------------
# Auth / token expiry detection
# ---------------------------------------------------------------------------
class AuthError(RuntimeError):
    """Raised when Slack/Supabase auth is missing, expired, or rejected."""


# Slack Web API error codes that mean "your token won't work" — never silent.
AUTH_ERROR_CODES = frozenset(
    {
        "invalid_auth",
        "not_authed",
        "account_inactive",
        "token_expired",
        "token_revoked",
        "no_permission",
        "missing_scope",
        "ekm_access_denied",
    }
)

# Substrings that signal an auth/JWT problem from Supabase or generic HTTP layers.
_AUTH_MESSAGE_NEEDLES = (
    "token_expired",
    "jwt expired",
    "invalid jwt",
    "invalid_auth",
    "not authenticated",
    "unauthorized",
    "401",
    "permission denied",
)


def classify_auth_error(exc: BaseException) -> Optional[str]:
    """Return a normalized auth error code if ``exc`` looks like auth failure.

    Recognises ``slack_sdk.errors.SlackApiError`` (via its ``.response`` payload)
    and message-based Supabase/HTTP failures. Returns ``None`` when the error is
    not auth-related, so callers can distinguish "auth broke" from other faults.
    """
    response = getattr(exc, "response", None)
    if response is not None:
        code = None
        try:
            code = response.get("error")  # SlackResponse / dict
        except (AttributeError, TypeError):
            code = None
        if isinstance(code, str) and code in AUTH_ERROR_CODES:
            return code

    message = str(exc).lower()
    for needle in _AUTH_MESSAGE_NEEDLES:
        if needle in message:
            return needle.replace(" ", "_")
    return None


def verify_slack_auth(client, logger: Optional[logging.Logger] = None) -> dict:
    """Call ``auth.test`` at startup; raise :class:`AuthError` on any failure.

    Returns the identity payload on success. This converts the most common
    silent-degradation mode (a bad/expired bot token) into a loud, logged,
    fail-fast at boot.
    """
    log = logger or _DEFAULT_LOGGER
    try:
        response = client.auth_test()
    except Exception as exc:  # noqa: BLE001 — classify then re-raise as AuthError
        code = classify_auth_error(exc) or "auth_test_failed"
        slog_error(log, "slack_auth_failed", code=code, error=type(exc).__name__, detail=str(exc))
        raise AuthError(f"Slack auth_test failed: {code}") from exc

    ok = True
    try:
        ok = bool(response.get("ok", True))
    except AttributeError:
        ok = True
    if not ok:
        code = None
        try:
            code = response.get("error")
        except AttributeError:
            code = None
        slog_error(log, "slack_auth_rejected", code=code or "unknown")
        raise AuthError(f"Slack auth_test returned not-ok: {code or 'unknown'}")

    team = bot_user = None
    try:
        team = response.get("team")
        bot_user = response.get("user")
    except AttributeError:
        pass
    slog_info(log, "slack_auth_ok", team=team, bot_user=bot_user)
    return response if isinstance(response, dict) else {"ok": True}


# ---------------------------------------------------------------------------
# In-flight worker tracking (for graceful shutdown)
# ---------------------------------------------------------------------------
class WorkerRegistry:
    """Spawn background workers as daemon threads while counting in-flight work.

    A drop-in replacement for ``threading.Thread(target=fn, daemon=True).start()``
    that lets shutdown drain outstanding work. Threads stay daemon so a hung
    worker can never block process exit past the drain timeout.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active = 0
        self._spawned = 0

    @property
    def active(self) -> int:
        with self._lock:
            return self._active

    @property
    def spawned(self) -> int:
        with self._lock:
            return self._spawned

    def spawn(
        self,
        target: Callable,
        *args,
        name: Optional[str] = None,
        **kwargs,
    ) -> threading.Thread:
        def _wrapped() -> None:
            try:
                target(*args, **kwargs)
            finally:
                with self._lock:
                    self._active -= 1

        with self._lock:
            self._active += 1
            self._spawned += 1
        thread = threading.Thread(target=_wrapped, name=name, daemon=True)
        thread.start()
        return thread

    def drain(
        self,
        timeout: float = 8.0,
        poll: float = 0.1,
        logger: Optional[logging.Logger] = None,
    ) -> bool:
        """Block up to ``timeout`` seconds for in-flight workers to finish.

        Returns True if everything drained, False on timeout (caller decides
        whether to exit anyway — workers are daemon threads either way).
        """
        log = logger or _DEFAULT_LOGGER
        deadline = time.monotonic() + max(0.0, timeout)
        remaining = self.active
        if remaining:
            slog_info(log, "worker_drain_start", inflight=remaining, timeout=timeout)
        while self.active > 0 and time.monotonic() < deadline:
            time.sleep(poll)
        remaining = self.active
        if remaining:
            slog_warning(log, "worker_drain_timeout", inflight=remaining, timeout=timeout)
            return False
        slog_info(log, "worker_drain_complete")
        return True


# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
class GracefulShutdown:
    """Run an ordered set of shutdown hooks on SIGTERM/SIGINT, exactly once."""

    def __init__(self, logger: Optional[logging.Logger] = None, exit_on_signal: bool = True) -> None:
        self._logger = logger or _DEFAULT_LOGGER
        self._callbacks: list[Tuple[str, Callable[[], None]]] = []
        self._fired = threading.Event()
        self._lock = threading.Lock()
        self._exit_on_signal = exit_on_signal

    @property
    def fired(self) -> bool:
        return self._fired.is_set()

    def register(self, name: str, callback: Callable[[], None]) -> None:
        """Register a hook. Hooks run in registration order during shutdown."""
        self._callbacks.append((name, callback))

    def install(self, signals: Iterable[int] = (signal.SIGTERM, signal.SIGINT)) -> None:
        """Install signal handlers. Must be called from the main thread."""
        for sig in signals:
            signal.signal(sig, self._handle_signal)

    def run(self, signum: Optional[int] = None) -> bool:
        """Run all hooks once (idempotent). Returns True if this call fired them."""
        with self._lock:
            if self._fired.is_set():
                return False
            self._fired.set()
        slog_info(self._logger, "shutdown_begin", signal=signum)
        for name, callback in self._callbacks:
            try:
                callback()
            except Exception as exc:  # noqa: BLE001 — one bad hook must not abort the rest
                slog_error(self._logger, "shutdown_hook_error", hook=name, error=type(exc).__name__, detail=str(exc))
            else:
                slog_info(self._logger, "shutdown_hook_done", hook=name)
        slog_info(self._logger, "shutdown_complete")
        return True

    def _handle_signal(self, signum, _frame) -> None:
        self.run(signum=signum)
        if self._exit_on_signal:
            # Raising SystemExit in the main thread unwinds blocking calls
            # (e.g. SocketModeHandler.start()) so the process exits cleanly.
            raise SystemExit(0)


# ---------------------------------------------------------------------------
# Metrics (dependency-free Prometheus text exposition)
# ---------------------------------------------------------------------------
def _labels_key(labels: Dict[str, str]) -> Tuple[Tuple[str, str], ...]:
    return tuple(sorted((str(k), str(v)) for k, v in labels.items()))


def _render_labels(label_key: Tuple[Tuple[str, str], ...]) -> str:
    if not label_key:
        return ""
    inner = ",".join(f'{k}="{_escape_label(v)}"' for k, v in label_key)
    return "{" + inner + "}"


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


class Metrics:
    """Minimal in-process counter/gauge registry rendering Prometheus text.

    No external dependency (``prometheus_client`` is not installed). Enough for
    Tier-1 observability: command + persistence counters and an in-flight gauge.
    Dynamic gauges (``register_gauge_fn``) are sampled at render time.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._gauges: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self._gauge_fns: Dict[str, Callable[[], float]] = {}
        self._help: Dict[str, str] = {}

    def describe(self, name: str, help_text: str) -> None:
        with self._lock:
            self._help[name] = help_text

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, _labels_key(labels))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        key = (name, _labels_key(labels))
        with self._lock:
            self._gauges[key] = float(value)

    def register_gauge_fn(self, name: str, fn: Callable[[], float]) -> None:
        with self._lock:
            self._gauge_fns[name] = fn

    def render(self) -> str:
        lines: list[str] = []
        with self._lock:
            counters = dict(self._counters)
            gauges = dict(self._gauges)
            gauge_fns = dict(self._gauge_fns)
            helps = dict(self._help)

        emitted_type: set[str] = set()

        def _emit_header(name: str, metric_type: str) -> None:
            if name in emitted_type:
                return
            emitted_type.add(name)
            if name in helps:
                lines.append(f"# HELP {name} {helps[name]}")
            lines.append(f"# TYPE {name} {metric_type}")

        for (name, label_key), value in sorted(counters.items()):
            _emit_header(name, "counter")
            lines.append(f"{name}{_render_labels(label_key)} {_fmt(value)}")

        for (name, label_key), value in sorted(gauges.items()):
            _emit_header(name, "gauge")
            lines.append(f"{name}{_render_labels(label_key)} {_fmt(value)}")

        for name, fn in sorted(gauge_fns.items()):
            try:
                value = float(fn())
            except Exception:  # noqa: BLE001 — a broken sampler must not break /metrics
                continue
            _emit_header(name, "gauge")
            lines.append(f"{name} {_fmt(value)}")

        return "\n".join(lines) + ("\n" if lines else "")


def _fmt(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(value)


def start_metrics_server(
    metrics: Metrics,
    port: int,
    addr: str = "127.0.0.1",
    logger: Optional[logging.Logger] = None,
):
    """Serve ``metrics.render()`` at ``GET /metrics`` on a daemon thread.

    Bound to localhost by default — scrape via the host's existing reverse proxy
    rather than exposing the port directly. Returns the HTTPServer (call
    ``.shutdown()`` to stop) or None if the socket could not be bound.
    """
    from http.server import BaseHTTPRequestHandler, HTTPServer

    log = logger or _DEFAULT_LOGGER

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 — stdlib naming
            if self.path.split("?", 1)[0] != "/metrics":
                self.send_response(404)
                self.end_headers()
                return
            body = metrics.render().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):  # silence per-request stderr spam
            return

    try:
        httpd = HTTPServer((addr, port), _Handler)
    except OSError as exc:
        slog_error(log, "metrics_server_bind_failed", addr=addr, port=port, error=str(exc))
        return None
    threading.Thread(target=httpd.serve_forever, name="commander-metrics-http", daemon=True).start()
    slog_info(log, "metrics_server_started", addr=addr, port=port)
    return httpd
