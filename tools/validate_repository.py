from __future__ import annotations

import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
REQUIRED_AGENT_KEYS = ("name", "description", "developer_instructions")
SKILL_FRONTMATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def frontmatter_value(body: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", body)
    if not match:
        return None
    return match.group(1).strip().strip('"\'')


def validate_skills() -> list[str]:
    errors: list[str] = []
    names: dict[str, Path] = {}
    skill_files = sorted((ROOT / ".agents" / "skills").glob("*/SKILL.md"))
    if len(skill_files) != 2:
        errors.append(f"expected 2 repository skills, found {len(skill_files)}")
    for path in skill_files:
        text = path.read_text(encoding="utf-8")
        match = SKILL_FRONTMATTER.match(text)
        if not match:
            errors.append(f"{path.relative_to(ROOT)}: missing frontmatter")
            continue
        body = match.group("body")
        name = frontmatter_value(body, "name")
        description = frontmatter_value(body, "description")
        if not name or not description:
            errors.append(f"{path.relative_to(ROOT)}: missing name or description")
            continue
        if name in names:
            errors.append(
                f"duplicate skill name {name!r}: "
                f"{names[name].relative_to(ROOT)} and {path.relative_to(ROOT)}"
            )
        names[name] = path
        if path.parent.name != name:
            errors.append(
                f"{path.relative_to(ROOT)}: directory does not match skill name {name!r}"
            )
    return errors


def validate_agents() -> list[str]:
    errors: list[str] = []
    names: dict[str, Path] = {}
    agents = sorted((ROOT / ".codex" / "agents").glob("*.toml"))
    if len(agents) != 6:
        errors.append(f"expected 6 custom agents, found {len(agents)}")
    for path in agents:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        for key in REQUIRED_AGENT_KEYS:
            if not data.get(key):
                errors.append(f"{path.relative_to(ROOT)}: missing {key}")
        name = data.get("name")
        if not name:
            continue
        if name in names:
            errors.append(
                f"duplicate agent name {name!r}: "
                f"{names[name].relative_to(ROOT)} and {path.relative_to(ROOT)}"
            )
        names[name] = path
    return errors


def validate_markdown_links() -> list[str]:
    errors: list[str] = []
    for markdown in ROOT.rglob("*.md"):
        if ".git" in markdown.parts:
            continue
        text = markdown.read_text(encoding="utf-8")
        for raw in MARKDOWN_LINK.findall(text):
            target = raw.strip("<>")
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            target = target.split("#", 1)[0]
            if target and not (markdown.parent / target).resolve().exists():
                errors.append(f"{markdown.relative_to(ROOT)}: missing link target {raw!r}")
    return errors


def main() -> int:
    errors = validate_skills() + validate_agents() + validate_markdown_links()
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("PASS: 2 repository skills, 6 custom agents, and local Markdown links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
