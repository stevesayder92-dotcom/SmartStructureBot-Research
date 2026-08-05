from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any
import gzip
import hashlib
import json
import re
import shutil

from simulator.config import load_config, project_root
from simulator.kernel.replay_session import ReplaySession
from simulator.models.financial import AccountConfig, ExecutionConfig
from simulator.services.data_library_service import DataLibraryService, parse_replay_time
from simulator.services.export_service import ExportService


SAFE_SESSION = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class ReplayBuildService:
    def __init__(self, root: Path | None = None):
        self.root = (root or project_root() / "simulator_runtime" / "sessions").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.library = DataLibraryService()
        self.jobs: dict[str, dict[str, Any]] = {}
        self._lock = Lock()

    def _set(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            self.jobs[job_id].update(updates)

    def start(self, request: dict[str, Any]) -> dict[str, Any]:
        symbol = str(request.get("symbol") or "")
        library = self.library.describe(symbol)
        start = parse_replay_time(request.get("start"))
        end = parse_replay_time(request.get("end"))
        available_start, available_end = self.library.available_range(symbol)
        if not available_start <= start < end <= available_end:
            raise ValueError("Requested replay range is outside the portable closed-candle library")
        max_events = request.get("max_events")
        if max_events is not None and not 1 <= int(max_events) <= 5000:
            raise ValueError("max_events must be between 1 and 5000")
        account = AccountConfig.from_dict(request.get("account_configuration"))
        execution = ExecutionConfig.from_dict(request.get("execution_configuration"))
        digest = hashlib.sha256(json.dumps({"symbol": symbol, "start": start, "end": end, "account": account.payload(), "execution": execution.payload()}, sort_keys=True).encode()).hexdigest()[:10]
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        session_id = f"S1B-{re.sub('[^A-Za-z0-9]', '', symbol)}-{stamp}-{digest}"
        job_id = f"JOB-{stamp}-{digest}"
        job = {
            "job_id": job_id,
            "session_id": session_id,
            "symbol": symbol,
            "status": "QUEUED",
            "stage": "VALIDATING_DATA",
            "progress_percent": 0.0,
            "processed_events": 0,
            "estimated_events": min(int((end - start) // 60 + 1), int(max_events or 5000)),
            "errors": [],
            "created_at": datetime.now(timezone.utc).isoformat(),
            "orders_enabled": False,
        }
        with self._lock:
            self.jobs[job_id] = job
        thread = Thread(target=self._run, args=(job_id, request, start, end, account, execution), daemon=True)
        thread.start()
        return dict(job)

    def _run(self, job_id: str, request: dict[str, Any], start: float, end: float, account: AccountConfig, execution: ExecutionConfig) -> None:
        try:
            self._set(job_id, status="RUNNING", stage="LOADING_PORTABLE_DATA", progress_percent=1.0)
            symbol = str(request["symbol"])
            dataset = self.library.load(symbol)
            session_id = self.jobs[job_id]["session_id"]
            self._set(job_id, stage="RUNNING_CANONICAL_PREFIX_PIPELINE", progress_percent=3.0)
            session = ReplaySession(
                dataset=dataset,
                config=load_config(),
                session_id=session_id,
                start_time=start,
                end_time=end,
                case_metadata={"source": "DYNAMIC_DATA_LIBRARY", "context_preload": int(request.get("context_preload", 180))},
                account_config=account,
                execution_config=execution,
            )

            def progress(done: int, total: int, stage: str) -> None:
                self._set(job_id, processed_events=done, estimated_events=total, stage=stage, progress_percent=3.0 + 87.0 * done / max(1, total))

            session.build(max_events=int(request["max_events"]) if request.get("max_events") is not None else None, progress_callback=progress)
            self._set(job_id, stage="SERIALIZING_IMMUTABLE_SESSION", progress_percent=92.0)
            destination = self.session_path(session_id)
            destination.mkdir(parents=True, exist_ok=False)
            raw = json.dumps(session.browser_payload(), separators=(",", ":")).encode("utf-8")
            (destination / "session.json.gz").write_bytes(gzip.compress(raw, compresslevel=6))
            (destination / "manifest.json").write_text(json.dumps(session.manifest(), indent=2, sort_keys=True), encoding="utf-8")
            exports = ExportService(session, destination / "exports")
            exports.export_financial()
            self._set(job_id, status="COMPLETE", stage="COMPLETE", progress_percent=100.0, event_count=len(session.events), completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as exc:
            self._set(job_id, status="FAILED", stage="FAILED", errors=[f"{type(exc).__name__}: {exc}"], completed_at=datetime.now(timezone.utc).isoformat())

    def status(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            if job_id not in self.jobs:
                raise KeyError("Unknown replay build job")
            return dict(self.jobs[job_id])

    def session_path(self, session_id: str) -> Path:
        if not SAFE_SESSION.fullmatch(session_id):
            raise ValueError("Invalid session id")
        candidate = (self.root / session_id).resolve()
        candidate.relative_to(self.root)
        return candidate

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = []
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            rows.append({"session_id": manifest["replay_session_id"], "symbol": manifest["symbol"], "event_count": manifest["event_count"], "status": "READY", "dynamic": True})
        return rows

    def delete(self, session_id: str) -> bool:
        target = self.session_path(session_id)
        if not target.exists():
            return False
        if target.parent != self.root or not target.name.startswith("S1B-"):
            raise RuntimeError("Only generated S1B sessions may be deleted")
        shutil.rmtree(target)
        return True
