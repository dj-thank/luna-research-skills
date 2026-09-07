from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPOSITORY_URL = "https://github.com/dj-thank/luna-research-skills"
SEMVER = re.compile(
    r"^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)"
    r"(?:-(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def _error(code: str, path: Path, message: str, root: Path) -> dict[str, str]:
    try:
        shown = path.relative_to(root).as_posix()
    except ValueError:
        shown = str(path)
    return {"code": code, "path": shown, "message": message}


def _read_utf8(path: Path, *, code: str, root: Path, errors: list[dict[str, str]]) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(_error(code, path, f"cannot read UTF-8 text: {exc}", root))
        return None


def validate_release_metadata(root: Path = ROOT) -> list[dict[str, str]]:
    root = Path(root).resolve()
    version_path = root / "VERSION"
    changelog_path = root / "CHANGELOG.md"
    errors: list[dict[str, str]] = []

    version_text = _read_utf8(
        version_path,
        code="version_read",
        root=root,
        errors=errors,
    )
    changelog = _read_utf8(
        changelog_path,
        code="changelog_read",
        root=root,
        errors=errors,
    )
    if version_text is None or changelog is None:
        return errors

    version = version_text.strip()
    if not SEMVER.fullmatch(version):
        errors.append(
            _error(
                "version_format",
                version_path,
                "VERSION must contain strict semantic versioning",
                root,
            )
        )
        return errors

    unreleased_heading_pattern = re.compile(r"(?m)^## \[Unreleased\]\s*$")
    unreleased_heading_count = len(unreleased_heading_pattern.findall(changelog))
    if unreleased_heading_count != 1:
        errors.append(
            _error(
                "changelog_unreleased_heading",
                changelog_path,
                "expected exactly one Unreleased heading",
                root,
            )
        )

    heading_pattern = re.compile(
        rf"(?m)^## \[{re.escape(version)}\] - "
        rf"(?P<date>\d{{4}}-\d{{2}}-\d{{2}})\s*$"
    )
    heading_count = len(heading_pattern.findall(changelog))
    if heading_count != 1:
        errors.append(
            _error(
                "changelog_version_heading",
                changelog_path,
                f"expected exactly one heading for VERSION {version}, found {heading_count}",
                root,
            )
        )
    else:
        heading_match = heading_pattern.search(changelog)
        assert heading_match is not None
        try:
            date.fromisoformat(heading_match.group("date"))
        except ValueError:
            errors.append(
                _error(
                    "changelog_version_date",
                    changelog_path,
                    f"VERSION {version} heading must use a valid ISO calendar date",
                    root,
                )
            )

    if heading_count == 1 and unreleased_heading_count == 1:
        version_start = heading_pattern.search(changelog)
        unreleased_start = unreleased_heading_pattern.search(changelog)
        assert version_start is not None and unreleased_start is not None
        if unreleased_start.start() > version_start.start():
            errors.append(
                _error(
                    "changelog_section_order",
                    changelog_path,
                    "Unreleased heading must appear before the current VERSION heading",
                    root,
                )
            )

    reference_pattern = re.compile(
        rf"(?m)^\[{re.escape(version)}\]:\s+"
        rf"{re.escape(REPOSITORY_URL)}/compare/v[^\s]+\.\.\."
        rf"v{re.escape(version)}\s*$"
    )
    reference_count = len(reference_pattern.findall(changelog))
    if reference_count != 1:
        errors.append(
            _error(
                "changelog_version_reference",
                changelog_path,
                "expected exactly one compare reference for "
                f"VERSION {version}, found {reference_count}",
                root,
            )
        )

    unreleased_pattern = re.compile(
        rf"(?m)^\[Unreleased\]:\s+{re.escape(REPOSITORY_URL)}/"
        rf"compare/v{re.escape(version)}\.\.\.HEAD\s*$"
    )
    unreleased_count = len(unreleased_pattern.findall(changelog))
    if unreleased_count != 1:
        errors.append(
            _error(
                "changelog_unreleased_base",
                changelog_path,
                f"Unreleased must compare from v{version} to HEAD exactly once",
                root,
            )
        )

    return errors


def main() -> int:
    errors = validate_release_metadata(ROOT)
    if errors:
        for error in errors:
            print("ERROR: " + json.dumps(error, ensure_ascii=False, sort_keys=True))
        return 1
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    print(f"PASS: VERSION {version} matches CHANGELOG heading and compare references")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
