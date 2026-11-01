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
    assert config["imports"] == []


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
