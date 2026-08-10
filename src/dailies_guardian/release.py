"""Build a deterministic, allowlisted candidate for the public contest repository."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil


PUBLIC_ROOT_FILES = (
    ".dockerignore",
    ".env.example",
    ".gitignore",
    "Dockerfile",
    "LICENSE",
    "README.md",
    "THIRD_PARTY_NOTICES.md",
    "pyproject.toml",
    "requirements.lock",
)

PUBLIC_DIRECTORIES = (
    ".github",
    "artifacts/public",
    "docs",
    "fixtures",
    "integration",
    "scripts",
    "src",
    "static",
    "tests",
)

# These are useful local handoff materials, but are neither application source nor
# judge-facing documentation. Keep them out of the public repository candidate.
INTERNAL_ONLY_PATHS = frozenset(
    {
        "docs/DEMO_STORYBOARD.md",
        "docs/DEVPOST_SUBMISSION_DRAFT.md",
        "docs/RUBRIC_AUDIT_DRAFT.md",
    }
)

NEVER_PUBLIC_PARTS = frozenset(
    {
        ".git",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "private",
    }
)

NEVER_PUBLIC_SUFFIXES = (".egg-info",)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_posix(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def iter_public_sources(source_root: Path) -> list[Path]:
    """Return every allowlisted source file in stable repository-path order."""

    source_root = source_root.resolve()
    candidates: list[Path] = []

    for relative in PUBLIC_ROOT_FILES:
        path = source_root / relative
        if not path.is_file():
            raise FileNotFoundError(f"Required public file is missing: {relative}")
        candidates.append(path)

    for relative in PUBLIC_DIRECTORIES:
        directory = source_root / relative
        if not directory.is_dir():
            raise FileNotFoundError(f"Required public directory is missing: {relative}")
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            public_path = _relative_posix(path, source_root)
            if public_path in INTERNAL_ONLY_PATHS:
                continue
            relative_parts = path.relative_to(source_root).parts
            if any(
                part in NEVER_PUBLIC_PARTS or part.endswith(NEVER_PUBLIC_SUFFIXES)
                for part in relative_parts
            ):
                continue
            if path.is_symlink():
                raise ValueError(
                    f"Symlinks are not allowed in the release candidate: {public_path}"
                )
            candidates.append(path)

    return sorted(set(candidates), key=lambda path: _relative_posix(path, source_root))


def build_public_release(source_root: Path, output_root: Path) -> dict[str, object]:
    """Copy the allowlist into a new directory and write its deterministic manifest.

    The destination must not already exist. This prevents a release build from
    deleting or silently retaining files from an earlier candidate.
    """

    source_root = source_root.resolve()
    output_root = output_root.resolve()
    unsafe_source_destination = output_root == source_root
    unexpected_in_tree_destination = (
        source_root in output_root.parents and output_root.name != "public-repo"
    )
    if unsafe_source_destination or unexpected_in_tree_destination:
        raise ValueError("Output inside the source tree must be named public-repo.")
    if output_root.exists():
        raise FileExistsError(
            "Release destination already exists; choose a new path or remove it "
            f"explicitly: {output_root}"
        )

    sources = iter_public_sources(source_root)
    output_root.mkdir(parents=True)
    records: list[dict[str, object]] = []

    for source in sources:
        relative = _relative_posix(source, source_root)
        destination = output_root / Path(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append(
            {
                "path": relative,
                "bytes": destination.stat().st_size,
                "sha256": _sha256(destination),
            }
        )

    manifest: dict[str, object] = {
        "schema_version": "1.0",
        "artifact": "dailies-guardian-public-repository-candidate",
        "manifest_scope": "Every candidate file except RELEASE_MANIFEST.json itself.",
        "generated_by": "python scripts/build_public_release.py",
        "files": records,
        "internal_only_paths_excluded": sorted(INTERNAL_ONLY_PATHS),
        "never_public_parts": sorted(NEVER_PUBLIC_PARTS),
        "never_public_suffixes": sorted(NEVER_PUBLIC_SUFFIXES),
    }
    manifest_path = output_root / "RELEASE_MANIFEST.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest
