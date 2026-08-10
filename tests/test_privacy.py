from __future__ import annotations

import os
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_SUFFIXES = {".md", ".py", ".toml", ".html", ".example", ".txt", ".json"}


class PublicTreePrivacyTests(unittest.TestCase):
    def test_public_tree_has_no_private_markers_or_credentials(self) -> None:
        forbidden = [
            re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
            re.compile(r"\b(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b"),
            re.compile(r"\b(?:10|127)\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
            re.compile(r"\b172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}\b"),
            re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
            re.compile(r"\b169\.254\.\d{1,3}\.\d{1,3}\b", re.I),
            re.compile(r"(?:AIza|ghp_|github_pat_)[A-Za-z0-9_\-]{16,}"),
        ]
        findings: list[str] = []
        for path in ROOT.rglob("*"):
            if (
                not path.is_file()
                or any(part in {".git", ".venv", "__pycache__"} for part in path.parts)
                or path.suffix not in PUBLIC_SUFFIXES
            ):
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in forbidden:
                if pattern.search(text):
                    findings.append(f"{path.relative_to(ROOT)}: {pattern.pattern}")
        self.assertEqual(findings, [])

    def test_project_runtime_has_no_disallowed_ai_vendor_imports(self) -> None:
        source = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (ROOT / "src").rglob("*.py")
        ).casefold()
        for forbidden in ("import openai", "from openai", "import anthropic", "from anthropic"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
