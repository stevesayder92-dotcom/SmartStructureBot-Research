from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import shutil
import zipfile

from simulator.config import project_root


SOURCE = project_root()
DELIVERY = SOURCE.parents[1] / "deliverables" / "SmartStructureBot_RealisticPaperAccount_20260803"
TARGET = DELIVERY / "SmartStructureBot_RealisticPaperAccount_Clean"
ZIP = DELIVERY / "SmartStructureBot_RealisticPaperAccount_Clean.zip"

EXCLUDED_DIRS = {
    ".git", ".pytest_cache", ".mypy_cache", "__pycache__", ".venv", "venv",
    "simulator_runtime", "simulator_reviews", "deliverables",
    "presimulator_repair_evidence", "final_fidelity_patch_v1_evidence",
    "final_prefix_causal_evidence", "phase10_evidence", "phase9_evidence",
    "sequence_elite_evidence",
}
EXCLUDED_SUFFIXES = {".pyc", ".pyo", ".tmp", ".log"}


def ignored(path: Path) -> bool:
    relative = path.relative_to(SOURCE)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return True
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    name = path.name.lower()
    if name.endswith(".bak") or name.startswith("backup_"):
        return True
    return False


def copy_clean() -> int:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    count = 0
    for path in sorted(SOURCE.rglob("*")):
        if ignored(path):
            continue
        relative = path.relative_to(SOURCE)
        destination = TARGET / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
        elif path.is_file():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            count += 1
    return count


def refresh_evidence_manifest() -> None:
    evidence = SOURCE / "phase_s1b_evidence"
    manifest = {}
    for path in sorted(evidence.rglob("*")):
        if path.is_file() and path.name != "evidence_hash_manifest.json":
            manifest[str(path.relative_to(evidence)).replace("\\", "/")] = sha256(path.read_bytes()).hexdigest()
    (evidence / "evidence_hash_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def make_zip() -> None:
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(TARGET.rglob("*")):
            if path.is_file():
                archive.write(path, Path(TARGET.name) / path.relative_to(TARGET))


def main() -> None:
    DELIVERY.mkdir(parents=True, exist_ok=True)
    refresh_evidence_manifest()
    files = copy_clean()
    make_zip()
    digest = sha256(ZIP.read_bytes()).hexdigest()
    report = {
        "status": "PASS",
        "source": str(SOURCE),
        "clean_tree": str(TARGET),
        "zip": str(ZIP),
        "file_count": files,
        "zip_bytes": ZIP.stat().st_size,
        "zip_sha256": digest,
        "orders_called": 0,
    }
    (DELIVERY / "PACKAGE_SHA256.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
