from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "src"))

from dailies_guardian.release import build_public_release  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublicReleaseTests(unittest.TestCase):
    def build_in(self, parent: Path, name: str = "candidate") -> tuple[Path, dict[str, object]]:
        output = parent / name
        return output, build_public_release(ROOT, output)

    def test_candidate_contains_runtime_assets_tests_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.build_in(Path(temporary))
            for relative in (
                ".github/workflows/public-release.yml",
                ".dockerignore",
                "LICENSE",
                "README.md",
                "THIRD_PARTY_NOTICES.md",
                "Dockerfile",
                "requirements.lock",
                "src/dailies_guardian/service.py",
                "static/index.html",
                "fixtures/telemetry_v1.json",
                "integration/grafana/dashboards/dailies-overview.json",
                "scripts/build_public_release.py",
                "tests/test_release.py",
                "docs/ARCHITECTURE.md",
                "docs/assets/dailies-guardian-dashboard.png",
                "artifacts/public/artifact_manifest_v1.json",
                "artifacts/public/evaluation_receipt_v1.json",
                "scripts/export_evaluation_receipt.py",
                "src/dailies_guardian/evaluation_receipt.py",
                "tests/test_evaluation_receipt.py",
            ):
                self.assertTrue((output / relative).is_file(), relative)

    def test_public_dashboard_screenshot_is_real_and_linked(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.build_in(Path(temporary))
            screenshot = output / "docs/assets/dailies-guardian-dashboard.png"
            payload = screenshot.read_bytes()
            self.assertEqual(payload[:8], b"\x89PNG\r\n\x1a\n")
            width, height = struct.unpack(">II", payload[16:24])
            self.assertGreaterEqual(width, 1400)
            self.assertGreaterEqual(height, 800)
            readme = (output / "README.md").read_text(encoding="utf-8")
            self.assertIn(
                "![Dailies Guardian synthetic incident console](docs/assets/dailies-guardian-dashboard.png)",
                readme,
            )

    def test_public_ci_is_credential_free_and_verifies_the_release_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.build_in(Path(temporary))
            workflow = (output / ".github/workflows/public-release.yml").read_text(
                encoding="utf-8"
            )
            for required in (
                "python -m unittest discover -s tests -v",
                "python -m compileall -q src tests fixtures",
                "python scripts/build_public_release.py",
                "docker build",
                "/healthz",
                "/api/fixture-cases",
                "id -u",
                "GRAFANA_URL=https://grafana.invalid",
                "GRAFANA_SERVICE_ACCOUNT_TOKEN=ci-placeholder-not-a-secret",
            ):
                self.assertIn(required, workflow)
            for forbidden in (
                "secrets.",
                "DAILIES_GOOGLE_API_KEY",
                "/analyze",
            ):
                self.assertNotIn(forbidden, workflow)
            self.assertIn('forbidden_exact = {".env",', workflow)
            self.assertIn('forbidden_prefixes = (".venv/", "artifacts/private/")', workflow)
            self.assertIn("relative.startswith(forbidden_prefixes)", workflow)
            self.assertNotIn('forbidden = (".env", ".venv"', workflow)

    def test_candidate_excludes_local_private_and_internal_handoff_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, manifest = self.build_in(Path(temporary))
            relative_files = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file()
            }
            self.assertNotIn(".env", relative_files)
            self.assertFalse(any(path.startswith(".venv/") for path in relative_files))
            self.assertFalse(any("__pycache__" in path for path in relative_files))
            self.assertFalse(any(".egg-info/" in path for path in relative_files))
            self.assertFalse(any(path.startswith("artifacts/private/") for path in relative_files))
            for excluded in manifest["internal_only_paths_excluded"]:
                self.assertNotIn(excluded, relative_files)
            self.assertIn(".env.example", relative_files)

    def test_candidate_contains_no_private_workspace_or_editable_install_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, _ = self.build_in(Path(temporary))
            text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.rglob("*")
                if path.is_file()
                and path.name != "RELEASE_MANIFEST.json"
                and path.suffix.casefold()
                in {
                    ".example",
                    ".html",
                    ".json",
                    ".lock",
                    ".md",
                    ".ps1",
                    ".py",
                    ".toml",
                    ".txt",
                    ".yaml",
                }
            )
            for forbidden in (
                str(ROOT),
                "git+" + "ssh://",
                "file:" + "///app",
                "bgrubbs1/" + "Bee.git",
            ):
                self.assertNotIn(forbidden.casefold(), text.casefold())
            self.assertIsNone(
                re.search(r"\b(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}\b", text)
            )

    def test_docker_context_excludes_local_and_internal_trees(self) -> None:
        patterns = {
            line.strip()
            for line in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for required in (
            ".git",
            ".venv",
            ".env",
            "artifacts",
            "docs",
            "dist",
            "integration",
            "tests",
        ):
            self.assertIn(required, patterns)

    def test_manifest_hashes_every_candidate_file_in_its_declared_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output, manifest = self.build_in(Path(temporary))
            records = manifest["files"]
            self.assertGreater(len(records), 30)
            for record in records:
                path = output / record["path"]
                self.assertEqual(path.stat().st_size, record["bytes"])
                self.assertEqual(sha256(path), record["sha256"])
            actual = {
                path.relative_to(output).as_posix()
                for path in output.rglob("*")
                if path.is_file() and path.name != "RELEASE_MANIFEST.json"
            }
            self.assertEqual(actual, {record["path"] for record in records})

    def test_two_release_builds_have_identical_manifests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary)
            first, _ = self.build_in(parent, "first")
            second, _ = self.build_in(parent, "second")
            self.assertEqual(
                (first / "RELEASE_MANIFEST.json").read_bytes(),
                (second / "RELEASE_MANIFEST.json").read_bytes(),
            )

    def test_existing_destination_is_never_deleted_or_merged(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("owner data\n", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                build_public_release(ROOT, output)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "owner data\n")


if __name__ == "__main__":
    unittest.main()
