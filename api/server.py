"""Command-center HTTP server (stdlib only) + static UI.

Routes:
    GET /                    -> ui/index.html
    GET /api/v1/executive    -> executive snapshot
    GET /api/v1/executions   -> recent closed trades
    GET /api/v1/decisions/{execution_id} -> full drill-down
    GET /api/v1/risk         -> risk/emergency/compliance state
    GET /api/v1/accounting   -> ledger balances + lots
    GET /api/v1/research     -> calibration report
    GET /api/v1/health       -> system health
    GET /metrics             -> Prometheus exposition

POST /api/v1/control/{action}  body {"operator_id","role",...params}
    -> audited ControlPlane execution
"""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from api.views import SystemSnapshotBuilder, prometheus_metrics
from core.control_plane import ControlPlane

logger = logging.getLogger(__name__)

_UI_FILE = Path(__file__).resolve().parents[1] / "ui" / "index.html"


def make_handler(
    builder: SystemSnapshotBuilder, control_plane: ControlPlane | None
) -> type[BaseHTTPRequestHandler]:
    """Bind views + control plane into a request handler class."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # quiet access logs
            logger.debug(fmt, *args)

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _text(self, text: str, status: int = 200, ctype: str = "text/plain") -> None:
            body = text.encode()
            self.send_response(status)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _stream(self, builder: SystemSnapshotBuilder, interval_s: float = 2.0) -> None:
            """Server-Sent Events: executive snapshot + platform tail every tick.

            Runs on this connection's worker thread until the client
            disconnects (broken pipe ends the loop). Stdlib only.
            """
            import time

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
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

        def do_GET(self) -> None:  # noqa: N802 - stdlib API
            path = self.path.split("?")[0]
            if path == "/" or path == "/ui":
                if _UI_FILE.exists():
                    self._text(_UI_FILE.read_text(encoding="utf-8"), ctype="text/html")
                else:
                    self._text("ui/index.html missing", status=404)
                return

            try:
                if path == "/api/v1/executive":
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
                    from urllib.parse import parse_qs, urlparse

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
                    from urllib.parse import parse_qs, urlparse

                    qs = parse_qs(urlparse(self.path).query)
                    lim = int((qs.get("limit") or ["100"])[0])
                    self._json({"events": builder.platform_feed(limit=lim)})
                elif path == "/api/v1/stream":
                    self._stream(builder)
                elif path == "/api/v1/models":
                    self._json(builder.models_view())
                elif path == "/api/v1/evaluations":
                    from urllib.parse import parse_qs, urlparse

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

        def do_POST(self) -> None:  # noqa: N802 - stdlib API
            path = self.path.split("?")[0]
            if path == "/api/v1/chat":
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    body = json.loads(raw or b"{}")
                    result = run_chat(
                        builder,
                        control_plane,
                        str(body.get("operator_id", "console")),
                        str(body.get("role", "OPERATOR")),
                        str(body.get("message", "")),
                    )
                    self._json(result)
                except Exception as exc:  # noqa: BLE001 - server boundary
                    logger.exception("chat failed")
                    self._json({"error": str(exc)}, status=500)
                return
            if control_plane is None or not path.startswith("/api/v1/control/"):
                self._json({"error": "not found"}, status=404)
                return
            action = path.rsplit("/", 1)[-1]
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                body = json.loads(raw or b"{}")
                result = run_control(control_plane, action, body)
                self._json(result)
            except PermissionError as exc:
                self._json({"error": str(exc)}, status=403)
            except (ValueError, RuntimeError, NotImplementedError) as exc:
                self._json({"error": str(exc)}, status=400)
            except Exception as exc:  # noqa: BLE001 - server boundary
                logger.exception("control action failed")
                self._json({"error": str(exc)}, status=500)

    def run_control(plane: ControlPlane, action: str, body: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        operator_id = str(body.get("operator_id", "")).strip()
        role = str(body.get("role", "VIEWER"))
        params_raw = body.get("params", {}) or {}
        params = {k: v for k, v in params_raw.items()}
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
    ) -> None:
        handler = make_handler(builder, control_plane)
        self._server = ThreadingHTTPServer(("127.0.0.1", port), handler)
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
