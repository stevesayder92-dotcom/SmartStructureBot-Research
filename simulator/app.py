from __future__ import annotations

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse
import gzip
import json
import mimetypes
import threading
import webbrowser

from simulator import SIMULATOR_VERSION, STRATEGY_VERSION
from simulator.config import project_root
from simulator.models.financial import AccountConfig, ExecutionConfig
from simulator.services.data_library_service import DataLibraryService
from simulator.services.execution_replay_service import PaperExecutionReplayService
from simulator.services.replay_build_service import ReplayBuildService


class SimulatorRequestHandler(SimpleHTTPRequestHandler):
    server_version = "SmartStructureBotSimulatorS1B/2.0"

    @property
    def root(self) -> Path:
        return Path(self.server.project_root)  # type: ignore[attr-defined]

    @property
    def builds(self) -> ReplayBuildService:
        return self.server.build_service  # type: ignore[attr-defined]

    @property
    def library(self) -> DataLibraryService:
        return self.server.data_library  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: object) -> None:
        print(f"[simulator] {self.address_string()} {format % args}")

    def _send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'")
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, payload: object, status: int = 200) -> None:
        self._send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def _read_json(self, maximum: int = 500_000) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > maximum:
            raise ValueError("Invalid request payload size")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON object required")
        return payload

    @staticmethod
    def _valid_identifier(value: str) -> bool:
        return bool(value) and value.replace("-", "").replace("_", "").isalnum()

    def _safe_static(self, request_path: str) -> Path | None:
        relative = request_path.lstrip("/") or "index.html"
        candidate = (self.root / "simulator" / "ui" / relative).resolve()
        ui_root = (self.root / "simulator" / "ui").resolve()
        try:
            candidate.relative_to(ui_root)
        except ValueError:
            return None
        return candidate

    def _session_source(self, session_id: str) -> Path | None:
        if not self._valid_identifier(session_id):
            return None
        runtime = self.builds.session_path(session_id) / "session.json.gz"
        if runtime.exists():
            return runtime
        curated = self.root / "simulator_evidence" / "sessions" / session_id / "session.json.gz"
        return curated if curated.exists() else None

    def _all_sessions(self) -> list[dict]:
        curated_path = self.root / "simulator_evidence" / "sessions" / "index.json"
        curated = json.loads(curated_path.read_text(encoding="utf-8")) if curated_path.exists() else []
        combined = {row["session_id"]: row for row in curated}
        for row in self.builds.list_sessions():
            combined[row["session_id"]] = row
        return sorted(combined.values(), key=lambda row: row["session_id"])

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        try:
            if path == "/api/health":
                return self._json({
                    "status": "PASS",
                    "orders": "DISABLED",
                    "paper_execution": "ENABLED_HISTORICAL_ONLY",
                    "strategy": STRATEGY_VERSION,
                    "simulator": SIMULATOR_VERSION,
                    "historical_closed_candles_only": True,
                    "order_api_calls": 0,
                })
            if path == "/api/sessions":
                return self._json(self._all_sessions())
            if path == "/api/data-library":
                return self._json({"symbols": self.library.list_symbols(), "configured_root_only": True})
            if path.startswith("/api/data-library/"):
                symbol = unquote(path.split("/api/data-library/", 1)[1])
                return self._json(self.library.describe(symbol))
            if path.startswith("/api/replay/build/") and path.endswith("/status"):
                job_id = path.split("/")[-2]
                return self._json(self.builds.status(job_id))
            if path.startswith("/api/replay/session/") or path.startswith("/api/session/"):
                session_id = unquote(path.rsplit("/", 1)[-1])
                source = self._session_source(session_id)
                if source is None:
                    return self._json({"error": "Session has not been built", "session_id": session_id}, 404)
                return self._send_bytes(gzip.decompress(source.read_bytes()), "application/json; charset=utf-8")
            static = self._safe_static(path)
            if static is None or not static.exists() or not static.is_file():
                return self._json({"error": "Not found"}, 404)
            content_type = mimetypes.guess_type(static.name)[0] or "application/octet-stream"
            return self._send_bytes(static.read_bytes(), content_type)
        except KeyError as exc:
            return self._json({"error": str(exc)}, 404)
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            payload = self._read_json(1_000_000)
            if path == "/api/replay/build":
                return self._json(self.builds.start(payload), 202)
            if path == "/api/paper/reprice":
                session_id = str(payload.get("session_id") or "")
                source = self._session_source(session_id)
                if source is None:
                    return self._json({"error": "Unknown replay session"}, 404)
                session_payload = json.loads(gzip.decompress(source.read_bytes()))
                result = PaperExecutionReplayService.reprice_browser_payload(
                    session_payload,
                    account_config=AccountConfig.from_dict(payload.get("account_configuration")),
                    execution_config=ExecutionConfig.from_dict(payload.get("execution_configuration")),
                    include_shadows=bool(payload.get("include_shadows", True)),
                )
                return self._json(result)
            if path == "/api/review":
                session_id = str(payload.get("session_id", ""))
                if not self._valid_identifier(session_id):
                    return self._json({"error": "Invalid session id"}, 400)
                reviews = self.root / "simulator_reviews"
                reviews.mkdir(exist_ok=True)
                target = reviews / f"{session_id}.json"
                target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
                return self._json({"saved": True, "path": str(target), "canonical_state_mutated": False})
            return self._json({"error": "Not found"}, 404)
        except json.JSONDecodeError:
            return self._json({"error": "Malformed JSON"}, 400)
        except KeyError as exc:
            return self._json({"error": str(exc)}, 404)
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, 400)
        except Exception as exc:
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        try:
            if not path.startswith("/api/replay/session/"):
                return self._json({"error": "Not found"}, 404)
            session_id = unquote(path.rsplit("/", 1)[-1])
            deleted = self.builds.delete(session_id)
            return self._json({"deleted": deleted, "session_id": session_id})
        except (ValueError, RuntimeError) as exc:
            return self._json({"error": str(exc)}, 400)


def serve(*, host: str = "127.0.0.1", port: int = 8765, open_browser: bool = True) -> None:
    root = project_root()
    server = ThreadingHTTPServer((host, int(port)), SimulatorRequestHandler)
    server.project_root = str(root)  # type: ignore[attr-defined]
    server.build_service = ReplayBuildService(root / "simulator_runtime" / "sessions")  # type: ignore[attr-defined]
    server.data_library = DataLibraryService(root / "simulator_data" / "library")  # type: ignore[attr-defined]
    url = f"http://{host}:{port}/"
    print("SmartStructureBot Phase S1B realistic paper-account simulator")
    print(f"Open: {url}")
    print("Historical paper simulation | estimated costs disclosed | live and demo orders disabled")
    if open_browser:
        threading.Timer(0.75, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
