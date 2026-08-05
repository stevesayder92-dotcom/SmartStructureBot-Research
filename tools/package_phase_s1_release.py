"""Build and verify the clean, portable Phase S1 research release."""

from __future__ import annotations

import hashlib
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RELEASE_PARENT = ROOT.parents[1] / "deliverables" / "SmartStructureBot_Simulator_PhaseS1_20260801"
RELEASE_NAME = "SmartStructureBot_Simulator_PhaseS1_Clean"
RELEASE_ROOT = RELEASE_PARENT / RELEASE_NAME
ZIP_PATH = RELEASE_PARENT / f"{RELEASE_NAME}.zip"

EXCLUDED_ROOTS = {
    ".git",
    ".venv",
    "__pycache__",
    "simulator_evidence",
    "final_fidelity_patch_v1_evidence",
    "final_prefix_causal_evidence",
    "presimulator_repair_evidence",
    "sequence_elite_evidence",
}
BASELINE_AUDITS = {
    "final_fidelity_patch_v1_evidence": "final_fidelity_patch_v1_audit.json",
    "presimulator_repair_evidence": "presimulator_repair_audit.json",
}
TOP_EVIDENCE_FILES = {
    "acceptance_scenarios.json",
    "baseline_test_output.txt",
    "curated_sessions_manifest.json",
    "investor_demo_manifest.json",
    "performance_benchmark.json",
    "phase_s1_release_audit.json",
    "phase_s1_test_output.txt",
    "phase_s1_visual_review.html",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ignore(directory: str, names: list[str]) -> set[str]:
    path = Path(directory)
    ignored: set[str] = set()
    for name in names:
        if name in EXCLUDED_ROOTS and path == ROOT:
            ignored.add(name)
        if name == "__pycache__" or name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored


def _safe_reset_generated_target() -> None:
    parent = RELEASE_PARENT.resolve()
    target = RELEASE_ROOT.resolve()
    if target.parent != parent or target.name != RELEASE_NAME:
        raise RuntimeError(f"Refusing to replace unexpected path: {target}")
    parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()


def _relative_session_row(row: dict) -> dict:
    clean = dict(row)
    sid = str(clean["session_id"])
    focus = int(clean.get("focus_event", 0))
    base = Path("simulator_evidence") / "sessions" / sid
    clean["manifest"] = str(base / "manifest.json")
    clean["event_export"] = str(base / "exports" / f"event_{focus:06d}.zip")
    clean["review_export"] = str(base / "exports" / f"chatgpt_review_{focus:06d}.zip")
    clean["sequence_export"] = str(base / "exports" / "sequence.zip")
    clean["full_replay_export"] = str(base / "exports" / "full_replay_session.zip")
    return clean


def _copy_evidence() -> list[dict]:
    source = ROOT / "simulator_evidence"
    destination = RELEASE_ROOT / "simulator_evidence"
    destination.mkdir(parents=True)
    for name in TOP_EVIDENCE_FILES:
        shutil.copy2(source / name, destination / name)
    shutil.copytree(source / "key_screenshots", destination / "key_screenshots")

    curated = json.loads((source / "curated_sessions_manifest.json").read_text(encoding="utf-8"))
    rows = [_relative_session_row(row) for row in curated["sessions"]]
    curated["sessions"] = rows
    curated["package_scope"] = "Twelve mandated curated sessions; supplemental build cases excluded."
    curated["portable_paths"] = True
    (destination / "curated_sessions_manifest.json").write_text(
        json.dumps(curated, indent=2), encoding="utf-8"
    )

    sessions_root = destination / "sessions"
    sessions_root.mkdir()
    for row in rows:
        sid = row["session_id"]
        session_source = source / "sessions" / sid
        session_destination = sessions_root / sid
        exports_destination = session_destination / "exports"
        exports_destination.mkdir(parents=True)
        shutil.copy2(session_source / "manifest.json", session_destination / "manifest.json")
        shutil.copy2(session_source / "session.json.gz", session_destination / "session.json.gz")
        for archive in (session_source / "exports").glob("*.zip"):
            shutil.copy2(archive, exports_destination / archive.name)
    (sessions_root / "index.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    return rows


def _copy_required_baseline_audits() -> None:
    for directory, filename in BASELINE_AUDITS.items():
        destination = RELEASE_ROOT / directory
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / directory / filename, destination / filename)


def _zip_release() -> None:
    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(RELEASE_ROOT.rglob("*")):
            if path.is_file():
                archive.write(path, Path(RELEASE_NAME) / path.relative_to(RELEASE_ROOT))


def _verify_zip(rows: list[dict]) -> dict:
    required = {
        f"{RELEASE_NAME}/README.md",
        f"{RELEASE_NAME}/SmartStructureBot_Bible.md",
        f"{RELEASE_NAME}/run_simulator.bat",
        f"{RELEASE_NAME}/simulator/ui/index.html",
        f"{RELEASE_NAME}/simulator_evidence/phase_s1_visual_review.html",
        f"{RELEASE_NAME}/simulator_evidence/phase_s1_release_audit.json",
    }
    for row in rows:
        sid = row["session_id"]
        required.update(
            {
                f"{RELEASE_NAME}/simulator_evidence/sessions/{sid}/manifest.json",
                f"{RELEASE_NAME}/simulator_evidence/sessions/{sid}/session.json.gz",
                f"{RELEASE_NAME}/simulator_evidence/sessions/{sid}/exports/full_replay_session.zip",
            }
        )
    with zipfile.ZipFile(ZIP_PATH) as archive:
        names = set(archive.namelist())
        missing = sorted(required - names)
        forbidden = sorted(
            name
            for name in names
            if "/__pycache__/" in name or name.endswith((".pyc", ".pyo")) or "/.git/" in name
        )
        bad_member = archive.testzip()
    if missing or forbidden or bad_member:
        raise RuntimeError(
            json.dumps(
                {"missing": missing, "forbidden": forbidden, "corrupt_member": bad_member}, indent=2
            )
        )
    return {
        "zip_entries": len(names),
        "required_entries": len(required),
        "missing_entries": 0,
        "forbidden_entries": 0,
        "corrupt_member": None,
    }


def main() -> None:
    _safe_reset_generated_target()
    shutil.copytree(ROOT, RELEASE_ROOT, ignore=_ignore)
    _copy_required_baseline_audits()
    rows = _copy_evidence()
    _zip_release()
    verification = _verify_zip(rows)
    digest = _sha256(ZIP_PATH)
    release_manifest = {
        "release": RELEASE_NAME,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "mode": "RESEARCH_ONLY",
        "orders_enabled": False,
        "orders_called": 0,
        "curated_sessions": len(rows),
        "zip_path": str(ZIP_PATH),
        "zip_bytes": ZIP_PATH.stat().st_size,
        "zip_sha256": digest,
        "verification": verification,
    }
    manifest_path = RELEASE_PARENT / "PHASE_S1_RELEASE_MANIFEST.json"
    checksum_path = RELEASE_PARENT / f"{ZIP_PATH.name}.sha256"
    manifest_path.write_text(json.dumps(release_manifest, indent=2), encoding="utf-8")
    checksum_path.write_text(f"{digest}  {ZIP_PATH.name}\n", encoding="utf-8")
    print(json.dumps(release_manifest, indent=2))


if __name__ == "__main__":
    main()
