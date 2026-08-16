#!/usr/bin/env python3
"""Build deterministic release artifacts using only the Python standard library."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parent.parent
EPOCH = (1980, 1, 1, 0, 0, 0)
EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox"}
EXCLUDED_NAMES = {".coverage", "coverage.xml"}
EXCLUDED_TOP_LEVEL = {"dist", "build", "reports", "artifacts", "release", "release-check"}
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
CANONICAL_TEXT_SUFFIXES = {".json", ".md", ".ps1", ".py", ".toml", ".txt", ".yaml", ".yml"}
CANONICAL_TEXT_NAMES = {".gitattributes", ".gitignore", "LICENSE", "VERSION"}


def version(root: Path) -> str:
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(value):
        raise ValueError("VERSION must contain strict semantic versioning")
    return value


def is_link_or_reparse(path: Path) -> bool:
    details = path.lstat()
    return path.is_symlink() or bool(
        getattr(details, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def tracked_files(root: Path) -> list[tuple[str, Path]]:
    try:
        listed = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            check=True,
            capture_output=True,
        ).stdout
        candidates = [Path(x.decode("utf-8")) for x in listed.split(b"\0") if x]
    except (OSError, subprocess.CalledProcessError):
        candidates = []
        for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            for dirname in list(dirnames):
                path = current_path / dirname
                if is_link_or_reparse(path):
                    raise ValueError(f"release source contains a symlink or reparse point: {path.relative_to(root).as_posix()}")
            for filename in filenames:
                path = current_path / filename
                if is_link_or_reparse(path):
                    raise ValueError(f"release source contains a symlink or reparse point: {path.relative_to(root).as_posix()}")
                candidates.append(path.relative_to(root))
    result = []
    for rel in candidates:
        if any(part in EXCLUDED_PARTS for part in rel.parts) or rel.name in EXCLUDED_NAMES:
            continue
        if rel.parts[0] in EXCLUDED_TOP_LEVEL:
            continue
        path = root / rel
        if path.is_file():
            if is_link_or_reparse(path):
                raise ValueError(f"release source contains a symlink or reparse point: {rel.as_posix()}")
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError as exc:
                raise ValueError(f"release source escapes repository: {rel.as_posix()}") from exc
            result.append((rel.as_posix(), path))
    return sorted(result)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_release_bytes(name: str, data: bytes) -> bytes:
    """Canonicalize UTF-8 text so one Git tree builds identically on every OS."""
    path = Path(name)
    if path.suffix.lower() not in CANONICAL_TEXT_SUFFIXES and path.name not in CANONICAL_TEXT_NAMES:
        return data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"release text source is not UTF-8: {name}") from exc
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def build(root: Path, output: Path) -> dict[str, Path]:
    ver = version(root)
    files = tracked_files(root)
    if not files:
        raise ValueError("no tracked source files found")
    if output.exists():
        if not output.is_dir() or any(output.iterdir()):
            raise ValueError(f"release output must be new or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    snapshot = []
    for name, path in files:
        source = path.read_bytes()
        snapshot.append((name, path, source, canonical_release_bytes(name, source)))
    stem = f"luna-skill-v{ver}"
    archive = output / f"{stem}.zip"
    def write_archive(path: Path, entries: list[tuple[str, bytes]]) -> None:
        if len(entries) != len({name for name, _ in entries}):
            raise ValueError(f"duplicate archive entry in {path.name}")
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as zf:
            for name, data in sorted(entries):
                info = zipfile.ZipInfo(name, date_time=EPOCH)
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                zf.writestr(info, data)
    write_archive(archive, [(name, data) for name, _, _, data in snapshot])
    plugin_name = f"luna-hierarchical-skills-{ver}-plugin.zip"
    plugin_entries: list[tuple[str, bytes]] = []
    manifest = {
        "name": "luna-hierarchical-skills",
        "version": ver,
        "description": "Bounded GPT-5.6 Luna research and mixed-delivery project skills for Codex.",
        "author": {
            "name": "dj-thank",
            "url": "https://github.com/dj-thank",
        },
        "homepage": "https://github.com/dj-thank/luna-research-skills",
        "repository": "https://github.com/dj-thank/luna-research-skills",
        "license": "MIT",
        "keywords": ["codex", "luna", "multi-agent", "research", "development"],
        "skills": "./skills/",
        "interface": {
            "displayName": "Luna Hierarchical Skills",
            "shortDescription": "Bounded Luna research and project teams",
            "longDescription": "Run evidence-only research or integrated development through bounded, runtime-verified GPT-5.6 Luna workstreams.",
            "developerName": "dj-thank",
            "category": "Developer Tools",
            "capabilities": ["Research", "Development", "Review"],
            "websiteURL": "https://github.com/dj-thank/luna-research-skills",
            "defaultPrompt": [
                "Research this topic with diverse Luna evidence scouts.",
                "Build and verify this project with bounded Luna workstreams.",
            ],
        },
    }
    plugin_entries.append((".codex-plugin/plugin.json", (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()))
    for name, _, _, data in snapshot:
        if name.startswith(".agents/skills/"):
            plugin_entries.append(("skills/" + name[len(".agents/skills/"):], data))
        elif name in {"LICENSE", "README.md", "SECURITY.md"}:
            plugin_entries.append((name, data))
    plugin_archive = output / plugin_name
    write_archive(plugin_archive, plugin_entries)
    inventory = []
    for name, _, _, data in snapshot:
        inventory.append({"SPDXID": f"SPDXRef-File-{hashlib.sha1(name.encode()).hexdigest()[:16]}", "fileName": name, "checksums": [{"algorithm": "SHA256", "checksumValue": hashlib.sha256(data).hexdigest()}]})
    sbom = output / f"{stem}.spdx.json"
    document = {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": stem,
        "documentNamespace": f"https://github.com/dj-thank/luna-research-skills/releases/tag/v{ver}#spdx",
        "creationInfo": {
            "created": "1980-01-01T00:00:00Z",
            "creators": ["Tool: tools/build_release.py"],
        },
        "documentDescribes": [item["SPDXID"] for item in inventory],
        "files": inventory,
        "packages": [],
    }
    sbom.write_text(json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8", newline="\n")
    sums = output / "SHA256SUMS"
    checksummed = (archive, plugin_archive, sbom)
    sums.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in checksummed),
        encoding="utf-8",
        newline="\n",
    )
    for name, path, source, _ in snapshot:
        if is_link_or_reparse(path) or path.read_bytes() != source:
            raise RuntimeError(f"release source changed during snapshot build: {name}")
    return {"archive": archive, "plugin": plugin_archive, "sums": sums, "sbom": sbom}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    outputs = build(args.root.resolve(), args.output.resolve())
    for path in outputs.values():
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
