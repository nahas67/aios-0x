"""Command-center HTTP server (stdlib only) + static UI.

Routes:
    GET /                    -> ui/dist/index.html (or ui/index.html fallback)
    GET /assets/*            -> ui/dist/assets/* (hashed, immutable cache)
    GET /favicon.svg         -> ui/dist/favicon.svg
    GET /api/v1/session/me   -> authenticated identity (operator_id, role)
    GET /api/v1/executive    -> executive snapshot
    GET /api/v1/executions   -> recent closed trades
    GET /api/v1/decisions/{execution_id} -> full drill-down
    GET /api/v1/risk         -> risk/emergency/compliance state
    GET /api/v1/accounting   -> ledger balances + lots
    GET /api/v1/research     -> calibration report
    GET /api/v1/health       -> system health (unauthenticated)
    GET /metrics             -> Prometheus exposition

POST /api/v1/control/{action}  body {params}
    -> audited ControlPlane execution (identity from bearer token)
POST /api/v1/chat  body {message}
    -> operator console chat (identity from bearer token)

SECURITY MODEL:
    The bearer token is mapped server-side to a canonical (operator_id, role).
    Client-supplied operator_id/role in POST bodies are IGNORED for
    authorization — the server-resolved identity is authoritative.
"""

import hmac
import json
import logging
import os
import threading
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from api.views import SystemSnapshotBuilder, prometheus_metrics
from core.control_plane import ControlPlane
from core.financial_kernel import FinancialStoreError

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1]
_DIST_DIR = _ROOT / "ui" / "dist"
_LEGACY_UI = _ROOT / "ui" / "index.html"

# SPA index: prefer compiled dist, fall back to legacy single-file HTML.
_UI_INDEX = _DIST_DIR / "index.html" if (_DIST_DIR / "index.html").exists() else _LEGACY_UI

MAX_REQUEST_BYTES = 64 * 1024

# Safe MIME map — no executable types; only what Vite produces + favicon.
_MIME: dict[str, str] = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
    ".ttf": "font/ttf",
    ".map": "application/json",
}

# Security headers applied to every response.
_SECURITY_HEADERS: list[tuple[str, str]] = [
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=()"),
    (
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'none'; form-action 'self'",
    ),
]


# ---------------------------------------------------------------------------
# Server-side identity model
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ServerIdentity:
    """Immutable identity resolved from a server-side credential mapping."""

    operator_id: str
    role: str  # canonical role string, e.g. "ADMIN"


_VALID_ROLES = frozenset({"VIEWER", "OPERATOR", "RISK_ADMIN", "ADMIN"})
_ANONYMOUS_IDENTITY = ServerIdentity(operator_id="anonymous", role="VIEWER")
_token_identity_map: dict[str, ServerIdentity] = {}


def _normalise_identity(value: object, fallback_operator: str = "principal") -> ServerIdentity | None:
    """Validate identity configuration without ever trusting request data."""
    if isinstance(value, str):
        operator_id = fallback_operator
        role = value
    elif isinstance(value, Mapping):
        operator_id = str(value.get("operator_id", fallback_operator))
        role = str(value.get("role", "VIEWER"))
    else:
        return None

    operator_id = operator_id.strip()[:128]
    role = role.strip().upper()
    if not operator_id or role not in _VALID_ROLES:
        return None
    return ServerIdentity(operator_id=operator_id, role=role)


def _configured_default_identity() -> ServerIdentity:
    """Resolve the single-token identity from server configuration.

    A configured token without an explicit role is intentionally VIEWER. This
    prevents a legacy shared token from silently acquiring administrative
    authority during a deployment migration.
    """
    identity = _normalise_identity(
        {
            "operator_id": os.environ.get("AIOS_OPERATOR_ID", "principal"),
            "role": os.environ.get("AIOS_DEFAULT_ROLE", "VIEWER"),
        }
    )
    return identity or _ANONYMOUS_IDENTITY


def parse_token_map(raw: str | None) -> dict[str, ServerIdentity]:
    """Parse a server-owned token map without logging credentials."""
    parsed: dict[str, ServerIdentity] = {}
    if not raw:
        return parsed
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("AIOS_TOKEN_MAP is not valid JSON; token-map entries disabled")
        return parsed
    if not isinstance(decoded, dict):
        logger.warning("AIOS_TOKEN_MAP must be a JSON object; token-map entries disabled")
        return parsed

    for configured_token, configured_identity in decoded.items():
        if not isinstance(configured_token, str) or not configured_token:
            continue
        identity = _normalise_identity(configured_identity)
        if identity is not None:
            parsed[configured_token] = identity
    return parsed


def _init_token_map(raw: str | None = None) -> dict[str, ServerIdentity]:
    """Load the process token map from environment or explicit settings."""
    global _token_identity_map  # noqa: PLW0603
    configured_raw = os.environ.get("AIOS_TOKEN_MAP", "") if raw is None else raw
    _token_identity_map = parse_token_map(configured_raw)
    return _token_identity_map



def resolve_identity(
    token: str,
    auth_token: str | None,
    identity_map: Mapping[str, ServerIdentity] | None = None,
    default_identity: ServerIdentity | None = None,
) -> ServerIdentity | None:
    """Map a bearer token to a canonical server-side identity.

    Identity and role are resolved exclusively from server configuration. The
    browser cannot submit either field to this function. ``identity_map`` is
    iterated with constant-time comparisons so multi-token deployments do not
    expose a privileged role through a client-controlled body field.
    """
    if not token:
        return None
    configured = identity_map if identity_map is not None else _token_identity_map
    for configured_token, identity in configured.items():
        if _constant_time_equal(token, configured_token):
            return identity
    if auth_token and _constant_time_equal(token, auth_token):
        return default_identity or _configured_default_identity()
    return None


def _constant_time_equal(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return hmac.compare_digest(a, b)


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

def _safe_resolve(dist_dir: Path, url_path: str) -> Path | None:
    """Resolve a URL path only when it remains inside the static root."""
    decoded = unquote(url_path)
    if "\x00" in decoded or any(ord(char) < 32 for char in decoded):
        return None
    base = dist_dir.resolve()
    try:
        resolved = (base / decoded.lstrip("/")).resolve()
        resolved.relative_to(base)
    except (ValueError, OSError):
        return None
    return resolved


def _serve_static(handler: BaseHTTPRequestHandler, dist_dir: Path, url_path: str) -> bool:
    """Serve a static file from dist_dir. Returns True if a file was served."""
    target = _safe_resolve(dist_dir, url_path)
    if target is None or not target.is_file():
        return False
    ext = target.suffix.lower()
    ctype = _MIME.get(ext, "application/octet-stream")
    body = target.read_bytes()
    handler.send_response(200)
    handler.send_header("X-Request-ID", handler.headers.get("X-Request-ID", "")[:128] or str(uuid.uuid4()))
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(len(body)))
    for hdr, val in _SECURITY_HEADERS:
        handler.send_header(hdr, val)
    # Vite hashes filenames in assets/ — immutable cache is safe.
    if "/assets/" in url_path:
        handler.send_header("Cache-Control", "public, max-age=31536000, immutable")
    else:
        handler.send_header("Cache-Control", "public, max-age=300")
    handler.end_headers()
    handler.wfile.write(body)
    return True


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------

def make_handler(
    builder: SystemSnapshotBuilder,
    control_plane: ControlPlane | None,
    auth_token: str | None = None,
    identity_map: Mapping[str, ServerIdentity] | None = None,
    default_identity: ServerIdentity | None = None,
) -> type[BaseHTTPRequestHandler]:
    """Bind views + control plane into a request handler class.

    Authentication is deliberately explicit: a missing token means an
    intentional unauthenticated *read-only* development server, while a
    configured token or token map protects every API mutation and stream.
    """
    configured_identities = dict(identity_map if identity_map is not None else _token_identity_map)
    configured_default = default_identity or _configured_default_identity()
    auth_required = bool(auth_token or configured_identities)

    class Handler(BaseHTTPRequestHandler):
        server_version = "AIOS/3.1"

        def log_message(self, fmt: str, *args: Any) -> None:  # quiet access logs
            logger.debug(fmt, *args)

        def _request_id(self) -> str:
            return self.headers.get("X-Request-ID", "")[:128] or str(uuid.uuid4())

        # --- Authentication & Identity ---

        def _extract_token(self) -> str:
            """Extract a bearer token only from the Authorization header."""
            supplied = self.headers.get("Authorization", "")
            scheme, separator, token = supplied.partition(" ")
            if not separator or scheme.lower() != "bearer":
                return ""
            return token.strip()

        def _resolve_request_identity(self) -> ServerIdentity | None:
            """Resolve identity exclusively from server-owned credential config."""
            token = self._extract_token()
            return resolve_identity(
                token,
                auth_token,
                identity_map=configured_identities,
                default_identity=configured_default,
            )

        def _authorized(self, path: str) -> bool:
            """Check if the request is authorized."""
            if path == "/api/v1/health" or not auth_required:
                return True
            return self._resolve_request_identity() is not None

        def _require_auth(self, path: str) -> bool:
            if self._authorized(path):
                return True
            self._json({"error": "authentication required"}, status=401)
            return False

        # --- Response helpers ---

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("X-Request-ID", self._request_id())
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for hdr, val in _SECURITY_HEADERS:
                self.send_header(hdr, val)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _text(self, text: str, status: int = 200, ctype: str = "text/plain") -> None:
            body = text.encode()
            self.send_response(status)
            self.send_header("X-Request-ID", self._request_id())
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            for hdr, val in _SECURITY_HEADERS:
                self.send_header(hdr, val)
            self.end_headers()
            self.wfile.write(body)

        # --- SSE (authenticated) ---

        def _stream(self, builder: SystemSnapshotBuilder, interval_s: float = 2.0) -> None:
            """Server-Sent Events: executive snapshot + platform tail every tick."""
            import time

            self.send_response(200)
            self.send_header("X-Request-ID", self._request_id())
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-store")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            for hdr, val in _SECURITY_HEADERS:
                self.send_header(hdr, val)
            self.end_headers()
            logger.info("SSE client connected: %s", self.client_address[0])
            try:
                while True:
                    payload = {
                        "ts": time.time(),
                        "executive": builder.executive(),
                        "platform_tail": builder.platform_feed(limit=10),
                    }
                    self.wfile.write(b"data: " + json.dumps(payload).encode() + b"\n\n")
                    self.wfile.flush()
                    time.sleep(interval_s)
            except (BrokenPipeError, ConnectionError, OSError):
                logger.info("SSE client disconnected: %s", self.client_address[0])

        def _request_length(self) -> int:
            raw_length = self.headers.get("Content-Length")
            try:
                length = int(raw_length or 0)
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length < 0 or length > MAX_REQUEST_BYTES:
                raise ValueError(f"request body exceeds {MAX_REQUEST_BYTES} bytes")
            return length

        def _json_body(self) -> dict[str, Any]:
            """Read one bounded JSON object and reject malformed input as 400."""
            length = self._request_length()
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
            except json.JSONDecodeError as exc:
                raise ValueError("request body must contain valid JSON") from exc
            if not isinstance(body, dict):
                raise ValueError("request body must be a JSON object")
            return body

        # --- GET routes ---

        def do_GET(self) -> None:  # noqa: N802 - stdlib API
            path = self.path.split("?")[0]

            # --- static file serving (unauthenticated — the login gate needs to load) ---
            if _DIST_DIR.exists():
                if path == "/" or path == "/ui":
                    if _serve_static(self, _DIST_DIR, "/index.html"):
                        return
                elif path.startswith("/assets/"):
                    if _serve_static(self, _DIST_DIR, path):
                        return
                elif path == "/favicon.svg":
                    if _serve_static(self, _DIST_DIR, "/favicon.svg"):
                        return

            # --- legacy fallback ---
            if path == "/" or path == "/ui":
                if _LEGACY_UI.exists():
                    self._text(_LEGACY_UI.read_text(encoding="utf-8"), ctype="text/html")
                else:
                    self._text("ui/index.html missing", status=404)
                return

            # SPA fallback
            if not path.startswith("/api") and not path.startswith("/metrics") and not path.startswith("/assets"):
                if _DIST_DIR.exists():
                    if _serve_static(self, _DIST_DIR, "/index.html"):
                        return

            # --- API routes (authenticated) ---
            if not self._require_auth(path):
                return

            try:
                if path == "/api/v1/session/me":
                    identity = self._resolve_request_identity()
                    if identity is None and not auth_required:
                        self._json(
                            {
                                "operator_id": "anonymous",
                                "role": "VIEWER",
                                "authenticated": False,
                                "auth_required": False,
                            }
                        )
                    elif identity is None:
                        self._json({"error": "authentication required"}, status=401)
                    else:
                        self._json(
                            {
                                "operator_id": identity.operator_id,
                                "role": identity.role,
                                "authenticated": True,
                                "auth_required": True,
                            }
                        )
                elif path == "/api/v1/executive":
                    self._json(builder.executive())
                elif path == "/api/v1/executions":
                    self._json({"executions": builder.executions()})
                elif path.startswith("/api/v1/decisions/"):
                    execution_id = path.rsplit("/", 1)[-1]
                    try:
                        self._json(builder.decision_drilldown(execution_id))
                    except KeyError:
                        self._json({"error": "unknown execution"}, status=404)
                elif path == "/api/v1/risk":
                    self._json(builder.risk_state())
                elif path == "/api/v1/accounting":
                    self._json(builder.accounting())
                elif path == "/api/v1/research":
                    self._json(builder.research_quality())
                elif path == "/api/v1/health":
                    self._json(builder.health())
                elif path == "/api/v1/settings":
                    self._json(builder.settings_view())
                elif path == "/api/v1/approvals":
                    self._json({"approvals": builder.approvals_view()})
                elif path == "/api/v1/positions":
                    self._json({"positions": builder.positions()})
                # ---- durable financial kernel (V1-A.2 read-only surface).
                # Read-only by design: no endpoint here can mutate the book. The
                # only financial mutation reachable over HTTP is the audited,
                # RBAC-gated lockout release below.
                elif path == "/api/v1/financial/ibor":
                    self._json(builder.ibor_view())
                elif path == "/api/v1/financial/positions":
                    self._json(builder.financial_positions())
                elif path == "/api/v1/financial/cash":
                    self._json(builder.financial_cash())
                elif path == "/api/v1/financial/orders":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["100"])[0])
                    self._json(builder.financial_orders(limit=lim))
                elif path.startswith("/api/v1/financial/orders/"):
                    order_id = path.rsplit("/", 1)[-1]
                    try:
                        self._json(builder.financial_order_detail(order_id))
                    except KeyError:
                        self._json({"error": "unknown order"}, status=404)
                elif path == "/api/v1/financial/fills":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["100"])[0])
                    self._json(builder.financial_fills(limit=lim))
                elif path == "/api/v1/financial/invariants":
                    self._json(builder.financial_invariants())
                elif path == "/api/v1/financial/health":
                    self._json(builder.financial_health())
                elif path == "/api/v1/financial/outbox":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["50"])[0])
                    self._json(builder.financial_outbox(limit=lim))
                elif path == "/api/v1/financial/reconciliation":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["20"])[0])
                    self._json(builder.financial_reconciliation(limit=lim))
                elif path == "/api/v1/portfolio":
                    self._json(builder.portfolio())
                elif path == "/api/v1/orders":
                    self._json({"orders": builder.orders()})
                elif path == "/api/v1/agents":
                    self._json({"agents": builder.agents()})
                elif path == "/api/v1/opportunities":
                    self._json({"opportunities": builder.opportunities()})
                elif path == "/api/v1/events":
                    self._json({"events": builder.events()})
                elif path == "/api/v1/regimes":
                    self._json({"regimes": builder.regimes()})
                elif path == "/api/v1/audit":
                    qs = parse_qs(urlparse(self.path).query)
                    q = (qs.get("q") or [""])[0]
                    lim = int((qs.get("limit") or ["50"])[0])
                    self._json({"audit": builder.audit(query=q, limit=lim)})
                elif path == "/api/v1/equity":
                    self._json(builder.equity())
                elif path == "/api/v1/pnl":
                    self._json(builder.pnl())
                elif path == "/api/v1/strategies":
                    self._json({"strategies": builder.strategies()})
                elif path == "/api/v1/alerts":
                    self._json({"alerts": builder.alerts()})
                elif path == "/api/v1/memory":
                    self._json(builder.memory_center())
                elif path == "/api/v1/graduation":
                    self._json(builder.graduation())
                elif path == "/api/v1/knowledge":
                    self._json(builder.knowledge())
                elif path.startswith("/api/v1/knowledge/"):
                    hypothesis_id = path.rsplit("/", 1)[-1]
                    try:
                        self._json(builder.hypothesis_detail(hypothesis_id))
                    except KeyError:
                        self._json({"error": "unknown hypothesis"}, status=404)
                elif path == "/api/v1/platform-events":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["100"])[0])
                    self._json({"events": builder.platform_feed(limit=lim)})
                elif path == "/api/v1/stream":
                    self._stream(builder)
                elif path == "/api/v1/models":
                    self._json(builder.models_view())
                elif path == "/api/v1/evaluations":
                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["50"])[0])
                    self._json({"evaluations": builder.evaluations_view(limit=lim)})
                elif path == "/api/v1/gates":
                    self._json(builder.gates_view())
                elif path == "/metrics":
                    self._text(prometheus_metrics(builder.executive()), ctype="text/plain")
                else:
                    self._json({"error": "not found"}, status=404)
            except Exception as exc:  # noqa: BLE001 - server boundary
                logger.exception("GET %s failed", path)
                self._json({"error": str(exc)}, status=500)

        # --- POST routes ---

        def do_POST(self) -> None:  # noqa: N802 - stdlib API
            path = self.path.split("?")[0]
            if not self._require_auth(path):
                return

            # Resolve server-side identity — NEVER trust client-supplied role/operator_id
            identity = self._resolve_request_identity()
            if identity is None:
                self._json({"error": "authentication required"}, status=401)
                return

            if path == "/api/v1/chat":
                try:
                    body = self._json_body()
                    message = body.get("message", "")
                    if not isinstance(message, str):
                        raise ValueError("message must be a string")
                    result = run_chat(
                        builder,
                        control_plane,
                        identity.operator_id,
                        identity.role,
                        message,
                    )
                    self._json(result)
                except (ValueError, TypeError) as exc:
                    self._json({"error": str(exc)}, status=400)
                except Exception:  # noqa: BLE001 - server boundary
                    logger.exception("chat failed")
                    self._json({"error": "chat request failed"}, status=500)
                return

            # --- durable safety-plane release (the only financial mutation here).
            # Authority comes from the server-resolved identity, never from the
            # request body: a caller-supplied "operator_id" proves nothing. The
            # role must hold RESET_LOCKOUT in the one authoritative RBAC matrix.
            if path.startswith("/api/v1/financial/lockouts/") and path.endswith("/release"):
                safety_plane = getattr(builder, "safety_plane", None)
                if safety_plane is None:
                    self._json({"error": "safety plane unavailable"}, status=503)
                    return
                lockout_id = path[len("/api/v1/financial/lockouts/") : -len("/release")]
                if not lockout_id or "/" in lockout_id:
                    self._json({"error": "invalid lockout id"}, status=400)
                    return
                try:
                    body = self._json_body()
                    note = body.get("note", "") if isinstance(body, dict) else ""
                    if not isinstance(note, str):
                        raise ValueError("note must be a string")
                    released = safety_plane.release(
                        lockout_id,
                        operator_id=identity.operator_id,
                        role=str(identity.role),
                        note=note,
                    )
                    self._json(
                        {
                            "lockout_id": released.lockout_id,
                            "scope": str(released.scope),
                            "subject": released.subject,
                            "released_by": released.released_by,
                            "released_at": (
                                released.released_at.isoformat()
                                if released.released_at
                                else None
                            ),
                            "active": released.active,
                        }
                    )
                except PermissionError as exc:
                    self._json({"error": str(exc)}, status=403)
                except (ValueError, KeyError, FinancialStoreError) as exc:
                    self._json({"error": str(exc)}, status=400)
                except Exception:  # noqa: BLE001 - server boundary
                    logger.exception("lockout release failed")
                    self._json({"error": "lockout release failed"}, status=500)
                return

            if control_plane is None or not path.startswith("/api/v1/control/"):
                self._json({"error": "not found"}, status=404)
                return

            action = path.rsplit("/", 1)[-1]
            try:
                body = self._json_body()
                # Use server-resolved identity, NOT client-supplied operator_id/role
                result = run_control(
                    control_plane,
                    identity.operator_id,
                    identity.role,
                    action,
                    body,
                )
                self._json(result)
            except PermissionError as exc:
                self._json({"error": str(exc)}, status=403)
            except (ValueError, RuntimeError, NotImplementedError, KeyError) as exc:
                self._json({"error": str(exc)}, status=400)
            except Exception:  # noqa: BLE001 - server boundary
                logger.exception("control action failed")
                self._json({"error": "control action failed"}, status=500)

    def run_control(
        plane: ControlPlane,
        operator_id: str,
        role: str,
        action: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute a control action with server-resolved identity."""
        import asyncio

        if not isinstance(body, dict):
            raise ValueError("request body must be a JSON object")
        params_raw = body.get("params", {}) or {}
        if not isinstance(params_raw, dict):
            raise ValueError("params must be a JSON object")
        params = {str(k): v for k, v in params_raw.items()}

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(plane.execute(operator_id, role, action, params))
        finally:
            loop.close()

    def run_chat(
        builder: SystemSnapshotBuilder,
        control_plane: ControlPlane | None,
        operator_id: str,
        role: str,
        message: str,
    ) -> dict[str, Any]:
        """Execute a chat command with server-resolved identity."""
        import asyncio

        from core.chat_console import OperatorChat

        chat = OperatorChat(builder, control_plane)
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(chat.ask(operator_id, role, message))
        finally:
            loop.close()

    return Handler


class CommandCenterServer:
    """Daemon-threaded server; call start()/stop() around usage."""

    def __init__(
        self,
        builder: SystemSnapshotBuilder,
        control_plane: ControlPlane | None = None,
        port: int = 8787,
        auth_token: str | None = None,
        host: str = "127.0.0.1",
        identity_map: Mapping[str, ServerIdentity] | None = None,
        default_identity: ServerIdentity | None = None,
    ) -> None:
        configured_map = dict(identity_map) if identity_map is not None else _init_token_map()
        handler = make_handler(
            builder,
            control_plane,
            auth_token=auth_token,
            identity_map=configured_map,
            default_identity=default_identity,
        )
        self.host = host
        self._server = ThreadingHTTPServer((host, port), handler)
        self._server.timeout = 5.0
        self.port = self._server.server_address[1]
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def serve_forever(self) -> None:
        self._server.serve_forever()
