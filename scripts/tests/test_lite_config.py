import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULES_JSON = ROOT / "config" / "modules.json"


def load_modules_config():
    return json.loads(MODULES_JSON.read_text(encoding="utf-8"))


def test_modules_json_keys():
    config = load_modules_config()

    assert config["modules"] == [
        "platform",
        "agents",
        "packages/mcp-adapter",
        "packages/sdk-python",
        "pilot",
        "apps",
        "client",
        "scripts",
        "tools",
        "docker",
        "docs",
        "config",
    ]
    assert config["max_modules_per_task"] == 3
    assert type(config["max_modules_per_task"]) is int
    assert config["uncounted_modules"] == ["docs", "config"]
    assert config["unknown_module"] == "warn"
    assert isinstance(config["imports"], list) and 1 <= len(config["imports"]) <= 3


def test_import_rules_format_and_dirs():
    config = load_modules_config()
    modules = config["modules"]
    rules = config["imports"]

    assert isinstance(rules, list) and 1 <= len(rules) <= 3
    for rule in rules:
        assert isinstance(rule, dict)
        assert set(rule.keys()) in (
            {"from", "deny", "reason"},
            {"from", "allow", "reason"},
        )
        assert rule["from"] in modules
        assert os.path.isdir(os.path.join(ROOT, *rule["from"].split("/")))
        key = "deny" if "deny" in rule else "allow"
        targets = rule[key]
        assert isinstance(targets, list) and targets
        for target in targets:
            assert isinstance(target, str)
            assert target in modules
            assert target != rule["from"]
            assert os.path.isdir(os.path.join(ROOT, *target.split("/")))
        assert isinstance(rule["reason"], str) and rule["reason"].strip()


def test_modules_exist():
    config = load_modules_config()

    for module in config["modules"]:
        assert os.path.isdir(os.path.join(ROOT, *module.split("/"))), (
            f"Modulpfad fehlt: {module}"
        )


def test_uncounted_are_modules():
    config = load_modules_config()

    for module in config["uncounted_modules"]:
        assert module in config["modules"]


STRUCTURE_JSON = ROOT / "config" / "structure.json"

ALLOWED_GLOBS = {
    "platform/**",
    "agents/**",
    "packages/**",
    "pilot/**",
    "apps/**",
    "client/**",
    "scripts/**",
    "tools/**",
    "docs/**",
    "config/**",
    "docker/**",
    "tasks/**",
}

FORBIDDEN_GLOBS = {
    "platform/data/**",
    "**/*.log",
    "**/*.sqlite3",
    "**/*.db",
    ".venv/**",
    "*_out.txt",
}


def load_structure_config():
    return json.loads(STRUCTURE_JSON.read_text(encoding="utf-8"))


def test_structure_json_keys():
    config = load_structure_config()

    assert isinstance(config, dict)
    assert isinstance(config["_doc"], str)
    assert isinstance(config["allowed"], list) and config["allowed"]
    assert isinstance(config["forbidden"], list) and config["forbidden"]


def test_structure_entries():
    config = load_structure_config()

    for entry in config["allowed"]:
        assert isinstance(entry["glob"], str) and entry["glob"]
        assert isinstance(entry["kind"], str) and entry["kind"]
    for entry in config["forbidden"]:
        assert isinstance(entry["glob"], str) and entry["glob"]
        assert isinstance(entry["reason"], str) and entry["reason"]


def test_structure_globs():
    config = load_structure_config()
    allowed = [entry["glob"] for entry in config["allowed"]]
    forbidden = [entry["glob"] for entry in config["forbidden"]]

    assert len(allowed) == 12
    assert len(allowed) == len(set(allowed))
    assert set(allowed) == ALLOWED_GLOBS
    assert len(forbidden) == 6
    assert len(forbidden) == len(set(forbidden))
    assert set(forbidden) == FORBIDDEN_GLOBS
