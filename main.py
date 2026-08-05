from __future__ import annotations

import argparse
from pathlib import Path

from core.application_runtime import (
    format_application_report,
    run_from_config_file,
)


DEFAULT_CONFIG = (
    Path(__file__).resolve().parent
    / "config"
    / "research.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SmartStructureBot canonical research launcher"
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Path to the JSON runtime configuration",
    )
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    result = run_from_config_file(
        arguments.config
    )
    print(format_application_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
