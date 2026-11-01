"""Full-suite runner for Desk Lite and the landing gate. cwd-independent: the root is the folder above this script (the worktree).

The .venv holds editable installs that point at the main checkout. PYTHONPATH comes before .pth entries, so the worktree's src dirs
are put first, and the run refuses to continue if a package still resolves outside the root (a green for code the branch never touched).
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIRS = ("platform/src", "agents/src", "packages/mcp-adapter/src", "packages/sdk-python/src")
PACKAGES = ("agentswarm_platform", "agentswarm_agents", "agentswarm_mcp", "agentswarm_sdk")
TEST_DIRS = ("platform/tests", "agents/tests", "packages/mcp-adapter/tests", "pilot/news-hub/tests")


def build_env(env):
    src = [os.path.join(ROOT, d.replace("/", os.sep)) for d in SRC_DIRS]
    old = env.get("PYTHONPATH")
    return dict(env, PYTHONPATH=os.pathsep.join(src + ([old] if old else [])), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")


def stray_packages(python, env):
    """Names of packages that import from outside ROOT; [] when all resolve inside the worktree."""
    code = "import importlib,sys\nfor n in sys.argv[1:]: print(n, importlib.import_module(n).__file__)"
    out = subprocess.run([python, "-c", code, *PACKAGES], cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if out.returncode != 0:
        return [out.stderr.strip() or "import failed"]
    root = os.path.normcase(ROOT)
    return [line for line in out.stdout.splitlines() if not os.path.normcase(line.split(" ", 1)[1]).startswith(root + os.sep)]


def main():
    env = build_env(os.environ)
    stray = stray_packages(sys.executable, env)
    if stray:
        print("lite_full_suite: packages resolve outside the worktree, refusing to report green:", *stray, sep="\n  ")
        return 2
    dirs = [d for d in TEST_DIRS if os.path.isdir(os.path.join(ROOT, d))]
    if not dirs:
        print("lite_full_suite: no test dirs found, refusing to report green")
        return 2
    return subprocess.call([sys.executable, "-X", "utf8", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider", *dirs], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
