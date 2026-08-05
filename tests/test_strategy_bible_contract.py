from __future__ import annotations

import ast
from pathlib import Path
import unittest

from core.pipeline_runner import PipelineOptions
from core.runtime_config import RuntimeConfig
from core.steve_trade_management import SteveManagementConfig
from core.system_director import SystemStateDirector


ROOT = Path(__file__).resolve().parents[1]
BIBLE = ROOT / "SmartStructureBot_Bible.md"


class StrategyBibleContractTest(unittest.TestCase):
    def _text(self) -> str:
        return BIBLE.read_text(encoding="utf-8")

    def test_bible_exists_and_contains_required_sections(self):
        self.assertTrue(BIBLE.exists())
        text = self._text()
        for heading in (
            "# SmartStructureBot Bible",
            "## 3. Runtime architecture",
            "## 4. Director ownership",
            "## 9. Retracement lifecycle",
            "## 15. Trade management",
            "## 20. Replay contract",
            "## 23. Configurable parameters",
            "## 24. Test expectations",
            "## 26. Glossary",
        ):
            self.assertIn(heading, text)

    def test_bible_names_every_core_module(self):
        text = self._text()
        missing = [
            path.stem
            for path in (ROOT / "core").glob("*.py")
            if path.stem not in text
        ]
        self.assertEqual(missing, [])

    def test_bible_names_every_test_expectation(self):
        text = self._text()
        missing: list[str] = []
        for path in (ROOT / "tests").glob("test_*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.FunctionDef)
                    and node.name.startswith("test_")
                    and node.name not in text
                ):
                    missing.append(node.name)
        self.assertEqual(sorted(missing), [])

    def test_bible_documents_director_ownership_and_runtime_parameters(self):
        text = self._text()
        required_terms = {
            *SystemStateDirector.REQUIRED_SECTIONS,
            *SystemStateDirector.SECTION_OWNERS.values(),
            *RuntimeConfig.__dataclass_fields__,
            *PipelineOptions.__dataclass_fields__,
            *SteveManagementConfig.__dataclass_fields__,
        }
        missing = sorted(
            term for term in required_terms if str(term) not in text
        )
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
