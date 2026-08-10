from __future__ import annotations

from pathlib import Path
import hashlib
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "research_runs" / "s2a1"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    commands = [
        [sys.executable, "-m", "unittest", "tests.test_s2a1_m1_causality", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        [sys.executable, "-m", "unittest", "discover", "-s", "simulator/tests", "-v"],
    ]
    sections: list[str] = []
    results: list[dict] = []
    for command in commands:
        completed = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
        sections.append(f"$ {' '.join(command)}\n{completed.stdout}{completed.stderr}")
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "state": "PASS" if completed.returncode == 0 else "FAIL",
            }
        )
        print(f"{results[-1]['state']}: {' '.join(command[2:])}", flush=True)
    path = OUT / "full_test_results.txt"
    path.write_text("\n\n".join(sections), encoding="utf-8")
    manifest_path = OUT / "reproducibility_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["tests"] = results
        manifest.setdefault("outputs", {})[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": sha(path),
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
    return 0 if all(row["returncode"] == 0 for row in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
