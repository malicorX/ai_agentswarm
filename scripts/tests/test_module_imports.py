import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULES_JSON = ROOT / "config" / "modules.json"
SKIP_DIRS = {".venv", "__pycache__", "build", "dist", "node_modules", "target"}
SDK_BAD = "packages/sdk-python/src/agentswarm_sdk/bad.py"


def package_names(root: Path, module: str) -> list[str]:
    src = root / module / "src"
    if not src.is_dir():
        return []
    return sorted(
        p.name for p in src.iterdir() if p.is_dir() and (p / "__init__.py").is_file()
    )


def _skipped(rel_parts: tuple[str, ...]) -> bool:
    return any(part in SKIP_DIRS or part.endswith(".egg-info") for part in rel_parts)


def find_import_violations(
    root: Path, rules: list[dict], modules: list[str] | None = None
) -> list[str]:
    found: list[str] = []
    for rule in rules:
        if "deny" in rule:
            denied_modules = list(rule["deny"])
        else:
            allowed = {rule["from"], *rule.get("allow", [])}
            denied_modules = [m for m in (modules or []) if m not in allowed]
        packages = sorted(
            {pkg for mod in denied_modules for pkg in package_names(root, mod)}
        )
        if not packages:
            continue
        pattern = re.compile(
            r"^\s*(from|import)\s+(" + "|".join(map(re.escape, packages)) + r")(\.|\s|,|$)"
        )
        base = root / rule["from"]
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if _skipped(path.relative_to(base).parts):
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in enumerate(text.splitlines(), start=1):
                if pattern.match(line):
                    rel = path.relative_to(root).as_posix()
                    found.append(f"{rel}:{number}: {line.strip()}")
    return found


SDK_RULE = [{"from": "packages/sdk-python", "deny": ["agents"], "reason": "test"}]


def _make_dummy(tmp_path: Path, bad_text: str) -> None:
    init = tmp_path / "agents" / "src" / "agentswarm_agents" / "__init__.py"
    init.parent.mkdir(parents=True)
    init.write_text("", encoding="utf-8")
    bad = tmp_path / SDK_BAD
    bad.parent.mkdir(parents=True)
    bad.write_text(bad_text, encoding="utf-8")


def test_worktree_has_no_import_violations():
    config = json.loads(MODULES_JSON.read_text(encoding="utf-8"))

    assert len(config["imports"]) >= 1
    assert find_import_violations(ROOT, config["imports"], config["modules"]) == []


def test_dummy_violation_detected(tmp_path):
    _make_dummy(
        tmp_path, "import os\nfrom agentswarm_agents.client import repo_root\n"
    )

    found = find_import_violations(tmp_path, SDK_RULE)

    assert len(found) == 1
    assert f"{SDK_BAD}:2" in found[0]


def test_dummy_indented_import_detected(tmp_path):
    _make_dummy(tmp_path, "def f():\n    import agentswarm_agents\n")

    found = find_import_violations(tmp_path, SDK_RULE)

    assert len(found) == 1
    assert f"{SDK_BAD}:2" in found[0]


def test_dummy_clean_tree_passes(tmp_path):
    _make_dummy(
        tmp_path,
        "from agentswarm_platform.crypto import sign_payload\n# agentswarm_agents\n",
    )

    assert find_import_violations(tmp_path, SDK_RULE) == []


def test_dummy_prefix_name_not_matched(tmp_path):
    _make_dummy(tmp_path, "import agentswarm_agents_extra\n")

    assert find_import_violations(tmp_path, SDK_RULE) == []
