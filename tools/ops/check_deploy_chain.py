#!/usr/bin/env python3
"""Fail when a workflow commits data to main but is not chained to deploy.yml.

Commits pushed with the default GITHUB_TOKEN never fire `on: push`, so a
collection workflow's fresh JSON only reaches Cloudflare if deploy.yml lists
that workflow under `workflow_run`. Until 2026-09-24 only two of ~30 were
listed, and the hourly ticker went live once or twice a day, whenever an
unrelated deploy happened to run. This keeps a new collector from being
added without its deploy link.

Usage: python3 tools/ops/check_deploy_chain.py [--list]
  --list  print the names deploy.yml should chain, one per line, and exit 0
"""
import ast
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
WF = ROOT / ".github" / "workflows"
DEPLOY = WF / "deploy.yml"

# A push that lands on main: bare `git push`, or an explicit main target.
# Pushes to a review branch (`git push origin "$branch"`) do not count.
PUSH_TO_MAIN = re.compile(r"\bgit push\b(?:\s+origin\s+(?:HEAD:)?main\b)?\s*(?:$|&&|\|\||;|\))")


def workflow_name(text):
    m = re.search(r"^name:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip("'\"") if m else None


def pushes_to_main(text, root=ROOT):
    for line in text.splitlines():
        code = line.split("#", 1)[0]
        if PUSH_TO_MAIN.search(code):
            return True
    # A workflow may delegate its push to a checked-in publisher. Inspect
    # directly invoked Python scripts too, so moving a push cannot hide it.
    for script in re.findall(r"python3\s+['\"]([^'\"]+\.py)['\"]", text):
        path = (root / script).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'git':
                args = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
                if args[:3] == ['push', 'origin', 'HEAD:main']:
                    return True
    return False


def chained_names(text):
    m = re.search(r"workflow_run:\s*\n\s*workflows:\s*\n((?:\s+-\s+.+\n)+)", text)
    if not m:
        return set()
    return {re.sub(r"^\s*-\s*", "", l).strip().strip("'\"")
            for l in m.group(1).splitlines() if l.strip()}


def main():
    need = {}
    for f in sorted(WF.glob("*.yml")):
        if f == DEPLOY:
            continue
        text = f.read_text(encoding="utf-8")
        if pushes_to_main(text):
            need[workflow_name(text)] = f.name

    if "--list" in sys.argv:
        for name in sorted(need):
            print(name)
        return 0

    have = chained_names(DEPLOY.read_text(encoding="utf-8"))
    missing = sorted(set(need) - have)
    stale = sorted(have - set(need))
    for name in missing:
        print(f"::error file=.github/workflows/{need[name]}::'{name}' commits to main "
              "but is not in deploy.yml workflow_run.workflows -- its data never ships")
    for name in stale:
        print(f"::error file=.github/workflows/deploy.yml::deploy.yml chains '{name}', "
              "which no workflow is named (renamed or deleted?)")
    if missing or stale:
        return 1
    print(f"deploy.yml chains all {len(need)} workflows that commit to main")
    return 0


if __name__ == "__main__":
    sys.exit(main())
