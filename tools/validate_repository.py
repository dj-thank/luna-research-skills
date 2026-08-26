from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_AGENT_KEYS = ("name", "description", "developer_instructions")
SKILL_FRONTMATTER = re.compile(r"\A---\s*\n(?P<body>.*?)\n---\s*\n", re.DOTALL)
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
MAX_FILES = 5000
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
OBSOLETE_PATHS = {
    "PROMPT.md",
    "PROMPT.en.md",
    "PROJECT-PROMPT.md",
    "docs/luna-desktop-v2-workaround.md",
    "docs/research/luna-desktop-routing-2026-08-10.md",
}
TEXT_SUFFIXES = {".md", ".py", ".ps1", ".toml", ".yaml", ".yml", ".json"}
SENSITIVE_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "machine_user_path": re.compile(
        r"(?i)(?:\b[A-Z]:\\Users\\[^\\/:*?\"<>|\s]+\\|/(?:home|Users)/[^/\s'\"`]+/)"
    ),
}
ACTION_REF = re.compile(r"(?m)^\s*-?\s*uses:\s*[^\s@]+@([^\s#]+)")


def _error(code: str, path: Path | str, message: str, root: Path) -> dict[str, str]:
    try: shown = str(Path(path).relative_to(root))
    except (ValueError, TypeError): shown = str(path)
    return {"code": code, "path": shown, "message": message}


def _is_link_or_reparse(path: Path) -> bool:
    details = path.lstat()
    return path.is_symlink() or bool(
        getattr(details, "st_file_attributes", 0)
        & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    )


def _path_chain_has_reparse(path: Path, root: Path) -> bool:
    """Inspect lexical path components without resolving or following links."""
    root_abs = Path(os.path.abspath(root))
    cursor = Path(os.path.abspath(path))
    try:
        cursor.relative_to(root_abs)
    except ValueError:
        return True
    while True:
        if cursor.exists() or cursor.is_symlink():
            try:
                if _is_link_or_reparse(cursor):
                    return True
            except OSError:
                return True
        if cursor == root_abs:
            return False
        parent = cursor.parent
        if parent == cursor:
            return True
        cursor = parent


def frontmatter_value(body: str, key: str) -> str | None:
    match = re.search(rf"(?m)^{re.escape(key)}:\s*(.+?)\s*$", body)
    return match.group(1).strip().strip('"\'') if match else None


def _read_text(path: Path, root: Path, errors: list[dict[str, str]]) -> str | None:
    if _path_chain_has_reparse(path, root):
        errors.append(_error("reparse_source", path, "refusing to read through a symlink or reparse point", root))
        return None
    try: return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        errors.append(_error("read_error", path, f"cannot read UTF-8 text: {exc}", root)); return None


def _validate_openai_yaml(path: Path, text: str, root: Path, errors: list[dict[str, str]]) -> None:
    required = ("interface:", "  display_name:", "  short_description:", "  default_prompt:", "policy:", "  allow_implicit_invocation:")
    if any(line not in text for line in required):
        errors.append(_error("openai_yaml_shape", path, "expected interface display_name/short_description/default_prompt and policy allow_implicit_invocation", root))
    if not re.search(r"(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$", text):
        errors.append(_error("openai_yaml_policy", path, "allow_implicit_invocation must be boolean", root))


def _implicit_policy(text: str) -> bool | None:
    match = re.search(r"(?m)^\s*allow_implicit_invocation:\s*(true|false)\s*$", text)
    return None if match is None else match.group(1) == "true"


def validate_skills(root: Path = ROOT) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []; skills_dir = root / ".agents" / "skills"
    try: skill_files = sorted(skills_dir.glob("*/SKILL.md"))
    except OSError as exc: return [_error("io_error", skills_dir, str(exc), root)]
    if len(skill_files) != 2: errors.append(_error("skill_count", skills_dir, f"expected 2 repository skills, found {len(skill_files)}", root))
    names: dict[str, Path] = {}
    implicit: dict[str, bool | None] = {}
    for path in skill_files:
        text = _read_text(path, root, errors)
        if text is None: continue
        match = SKILL_FRONTMATTER.match(text)
        if not match: errors.append(_error("frontmatter", path, "missing frontmatter", root)); continue
        body = match.group("body"); name, description = frontmatter_value(body, "name"), frontmatter_value(body, "description")
        if not isinstance(name, str) or not name.strip() or not isinstance(description, str) or not description.strip():
            errors.append(_error("frontmatter_fields", path, "name and description must be non-empty strings", root)); continue
        key = name.casefold()
        if key in names: errors.append(_error("duplicate_skill_name", path, f"duplicate skill name {name!r} (case-insensitive)", root))
        names[key] = path
        if path.parent.name != name: errors.append(_error("skill_directory", path, f"directory does not match skill name {name!r}", root))
        yaml_path = path.parent / "agents" / "openai.yaml"
        if not yaml_path.is_file(): errors.append(_error("openai_yaml", yaml_path, "missing agents/openai.yaml", root)); continue
        yaml = _read_text(yaml_path, root, errors)
        if yaml is not None:
            _validate_openai_yaml(yaml_path, yaml, root, errors)
            implicit[name] = _implicit_policy(yaml)
        for required in (
            path.parent / "scripts" / "check_setup.py",
            path.parent / "scripts" / "test_check_setup.py",
        ):
            if not required.is_file():
                errors.append(_error("skill_contract_file", required, "missing required checker contract file", root))
    expected_implicit = {
        "run-diverse-luna-project": True,
        "run-diverse-luna-research": True,
    }
    if implicit and implicit != expected_implicit:
        errors.append(_error(
            "implicit_router",
            skills_dir,
            "both skills may be discoverable, but research must remain evidence-only and project delivery requires an explicit Luna implementation request",
            root,
        ))
    return errors


def validate_agents(root: Path = ROOT) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []; agents_dir = root / ".codex" / "agents"
    try: agents = sorted(agents_dir.glob("*.toml"))
    except OSError as exc: return [_error("io_error", agents_dir, str(exc), root)]
    if len(agents) != 5: errors.append(_error("agent_count", agents_dir, f"expected 5 non-built-in custom agents, found {len(agents)}", root))
    names: dict[str, Path] = {}
    for path in agents:
        if _path_chain_has_reparse(path, root):
            errors.append(_error("reparse_source", path, "refusing to parse agent TOML through a symlink or reparse point", root))
            continue
        try:
            with path.open("rb") as handle: data = tomllib.load(handle)
        except (OSError, UnicodeError, tomllib.TOMLDecodeError, ValueError) as exc:
            errors.append(_error("toml_error", path, f"invalid TOML: {exc}", root)); continue
        for key in REQUIRED_AGENT_KEYS:
            if not isinstance(data.get(key), str) or not data[key].strip(): errors.append(_error("agent_field", path, f"{key} must be a non-empty string", root))
        for key in ("model", "model_reasoning_effort", "service_tier", "sandbox_mode"):
            if key in data and (not isinstance(data[key], str) or not data[key].strip()):
                errors.append(_error("agent_field", path, f"{key} must be a non-empty string when present", root))
        if data.get("approval_policy") == "never":
            errors.append(_error("unsafe_agent_policy", path, "published agent definitions must not force approval_policy=never", root))
        name = data.get("name")
        if not isinstance(name, str) or not name.strip(): continue
        if name.casefold() in {"default", "worker", "explorer"}:
            errors.append(_error("builtin_agent_override", path, f"published custom agent must not shadow built-in role {name!r}", root))
        key = name.casefold()
        if key in names: errors.append(_error("duplicate_agent_name", path, f"duplicate agent name {name!r} (case-insensitive)", root))
        names[key] = path
    return errors


def _iter_files(root: Path, errors: list[dict[str, str]]) -> list[Path]:
    if (root / ".git").exists():
        try:
            result = subprocess.run(
                ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                check=True,
                capture_output=True,
            )
            visible = [root / Path(item.decode("utf-8")) for item in result.stdout.split(b"\0") if item]
            if len(visible) > MAX_FILES:
                errors.append(_error("scan_limit", root, f"file scan exceeded {MAX_FILES} files", root))
                return visible[:MAX_FILES]
            safe: list[Path] = []
            for path in visible:
                if _path_chain_has_reparse(path, root):
                    errors.append(_error("reparse_source", path, "Git-visible source is a symlink or reparse point", root))
                    continue
                try:
                    if path.is_file():
                        safe.append(path)
                except OSError as exc:
                    errors.append(_error("io_error", path, str(exc), root))
            return safe
        except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
            errors.append(_error("git_inventory", root, f"could not obtain Git-visible file inventory: {exc}", root))

    found: list[Path] = []
    try:
        for current, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            current_path = Path(current)
            safe_dirs: list[str] = []
            for dirname in dirnames:
                candidate = current_path / dirname
                if dirname == ".git":
                    continue
                try:
                    linked = _is_link_or_reparse(candidate)
                except OSError as exc:
                    errors.append(_error("io_error", candidate, str(exc), root)); continue
                if linked:
                    errors.append(_error("reparse_source", candidate, "repository directory is a symlink or reparse point", root))
                else:
                    safe_dirs.append(dirname)
            dirnames[:] = safe_dirs
            for filename in filenames:
                path = current_path / filename
                if len(found) >= MAX_FILES:
                    errors.append(_error("scan_limit", root, f"file scan exceeded {MAX_FILES} files", root))
                    return found
                try:
                    if _is_link_or_reparse(path):
                        errors.append(_error("reparse_source", path, "repository file is a symlink or reparse point", root))
                        continue
                except OSError as exc:
                    errors.append(_error("io_error", path, str(exc), root)); continue
                found.append(path)
    except OSError as exc: errors.append(_error("io_error", root, str(exc), root))
    return found


def validate_markdown_links(root: Path = ROOT) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []; total = 0
    for markdown in [p for p in _iter_files(root, errors) if p.suffix.lower() == ".md" and ".git" not in p.parts]:
        text = _read_text(markdown, root, errors)
        if text is None: continue
        for raw in MARKDOWN_LINK.findall(text):
            total += 1
            if total > MAX_FILES * 4: errors.append(_error("link_scan_limit", root, "Markdown link scan exceeded bound", root)); return errors
            target = raw.strip("<>").split("#", 1)[0].strip()
            if not target or target.startswith(("http://", "https://", "mailto:", "#")): continue
            lexical = Path(os.path.abspath(markdown.parent / target))
            try: lexical.relative_to(Path(os.path.abspath(root)))
            except ValueError: errors.append(_error("link_out_of_root", markdown, f"link target escapes repository: {raw!r}", root)); continue
            if _path_chain_has_reparse(lexical, root):
                errors.append(_error("link_reparse", markdown, f"local link traverses a symlink or reparse point: {raw!r}", root)); continue
            if not lexical.exists() or not (lexical.is_file() or lexical.is_dir()):
                errors.append(_error("missing_link", markdown, f"missing local link target {raw!r}", root))
    return errors


def validate_repository(root: Path = ROOT) -> list[dict[str, str]]:
    root = Path(root).resolve(); errors = validate_skills(root) + validate_agents(root) + validate_markdown_links(root)
    files = _iter_files(root, errors)
    for path in files:
        rel = path.relative_to(root)
        if "__pycache__" in rel.parts or path.suffix.lower() in {".pyc", ".pyo"}: errors.append(_error("compiled_artifact", path, "compiled Python artifacts are not allowed", root))
        if rel.as_posix() in OBSOLETE_PATHS:
            errors.append(_error("obsolete_path", path, "obsolete prompt/workaround path is not allowed", root))
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = _read_text(path, root, errors)
            if text is not None:
                for code, pattern in SENSITIVE_PATTERNS.items():
                    if pattern.search(text):
                        errors.append(_error(code, path, "potential secret or machine-specific path in public source", root))
                if path.parts[-3:-1] == (".github", "workflows"):
                    for reference in ACTION_REF.findall(text):
                        if not re.fullmatch(r"[0-9a-fA-F]{40}", reference):
                            errors.append(_error("unpinned_action", path, f"GitHub Action ref is not a full commit SHA: {reference}", root))
    research_scripts = root / ".agents" / "skills" / "run-diverse-luna-research" / "scripts"
    project_scripts = root / ".agents" / "skills" / "run-diverse-luna-project" / "scripts"
    for filename in ("check_setup.py", "test_check_setup.py"):
        research_file = research_scripts / filename
        project_file = project_scripts / filename
        if research_file.is_file() and project_file.is_file():
            if _path_chain_has_reparse(research_file, root) or _path_chain_has_reparse(project_file, root):
                errors.append(_error("reparse_source", research_file, "checker parity source traverses a reparse point", root))
            elif research_file.read_bytes() != project_file.read_bytes():
                errors.append(_error("checker_parity", research_file, f"research/project {filename} copies differ", root))
    version_path = root / "VERSION"
    if version_path.exists():
        value = (_read_text(version_path, root, errors) or "").strip()
        if not SEMVER.fullmatch(value):
            errors.append(_error("version", version_path, "VERSION must be strict semver", root))
        errors.extend(validate_release_workflow(root))
    _validate_plugin_manifest(root, errors)
    return errors


def validate_release_workflow(root: Path = ROOT) -> list[dict[str, str]]:
    """Require a manual, tag-bound, asset-complete, immutable release path."""
    errors: list[dict[str, str]] = []
    path = root / ".github" / "workflows" / "release.yml"
    if not path.is_file():
        return [_error("release_workflow", path, "VERSION requires a release workflow", root)]
    text = _read_text(path, root, errors)
    if text is None:
        return errors
    required = {
        "workflow_dispatch:": "release must require explicit workflow dispatch",
        'test "${GITHUB_REF_TYPE}" = "tag"': "release must run against a tag ref",
        "gh release create": "release workflow must create the GitHub Release",
        "release/*": "all verified release assets must be attached before publication",
        "--verify-tag": "release creation must refuse an absent remote tag",
        "--json isImmutable": "published release immutability must be verified",
        ".isImmutable": "published release immutability result must be asserted",
    }
    for marker, message in required.items():
        if marker not in text:
            errors.append(_error("release_workflow", path, message, root))
    if re.search(r"(?m)^\s*tags:\s*$", text):
        errors.append(_error("release_workflow", path, "pushing a tag must not publish automatically", root))
    return errors


def _validate_plugin_manifest(root: Path, errors: list[dict[str, str]]) -> None:
    path = root / ".codex-plugin" / "plugin.json"
    if not path.exists():
        return
    text = _read_text(path, root, errors)
    if text is None:
        return
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        errors.append(_error("plugin_manifest", path, f"invalid UTF-8 JSON: {exc}", root)); return
    if not isinstance(data, dict):
        errors.append(_error("plugin_manifest", path, "manifest must be a JSON object", root)); return
    for key in ("name", "version", "description", "author", "interface", "skills"):
        if key not in data: errors.append(_error("plugin_manifest", path, f"missing required field {key}", root))
    if not isinstance(data.get("name"), str) or not data.get("name", "").strip(): errors.append(_error("plugin_manifest", path, "name must be a non-empty string", root))
    if not isinstance(data.get("version"), str) or not SEMVER.fullmatch(data.get("version", "")): errors.append(_error("plugin_manifest", path, "version must be strict semver", root))
    if not isinstance(data.get("description"), str) or not data.get("description", "").strip(): errors.append(_error("plugin_manifest", path, "description must be a non-empty string", root))
    author = data.get("author")
    if not isinstance(author, dict) or not isinstance(author.get("name"), str) or not author.get("name", "").strip(): errors.append(_error("plugin_manifest", path, "author.name must be a non-empty string", root))
    interface = data.get("interface")
    if not isinstance(interface, dict): errors.append(_error("plugin_manifest", path, "interface must be an object", root))
    elif not all(isinstance(interface.get(k), str) and interface[k].strip() for k in ("displayName", "shortDescription")):
        errors.append(_error("plugin_manifest", path, "interface requires displayName and shortDescription strings", root))
    skills = data.get("skills")
    if not isinstance(skills, (str, list)) or (isinstance(skills, list) and not all(isinstance(v, str) for v in skills)):
        errors.append(_error("plugin_manifest", path, "skills must be a path string or list of strings", root)); return
    paths = [skills] if isinstance(skills, str) else skills
    if paths != ["./skills/"]:
        errors.append(_error("plugin_manifest", path, "packaged plugin skills must resolve exactly to ./skills/", root))


def main() -> int:
    try: errors = validate_repository(ROOT)
    except Exception as exc: errors = [_error("validator_error", ROOT, f"unexpected validator failure: {exc}", ROOT)]
    if errors:
        for error in errors: print("ERROR: " + json.dumps(error, ensure_ascii=False, sort_keys=True))
        return 1
    print("PASS: repository structure, metadata, links, and artifacts"); return 0


if __name__ == "__main__": raise SystemExit(main())
