#!/usr/bin/env python3
"""CI check: pyproject.toml and requirements.txt must declare the same direct
dependencies (audit 2026-11-11, F7).

pyproject.toml is the single source of truth; requirements.txt is the pinned
install file used by Docker/CI. Transitive pins in requirements.txt are
allowed via TRANSITIVE_DEPS, so the check only fails on genuine direct-dep
drift. Run: python scripts/check_dep_drift.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Pinned transitive dependencies in requirements.txt that are NOT direct
# dependencies in pyproject.toml. If a new direct dependency is added to
# requirements.txt, add it to pyproject.toml instead of this list.
TRANSITIVE_DEPS = {
    "annotated-types",
    "anyio",
    "certifi",
    "charset-normalizer",
    "h11",
    "idna",
    "pydantic-core",
    "six",
    "soupsieve",
    "starlette",
    "typing-inspection",
    "typing-extensions",
    "tzdata",
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pkg_name(spec: str) -> str:
    # strip environment markers, extras, version specifiers
    spec = spec.split(";", 1)[0].strip()
    m = re.match(r"^([A-Za-z0-9_.\-]+)(\[[^\]]*\])?", spec)
    return _norm(m.group(1)) if m else ""


def _pyproject_deps(text: str) -> set:
    # Line-based scan (a plain regex would stop at the ']' of pyjwt[crypto]).
    deps = []
    in_deps = False
    for line in text.splitlines():
        if not in_deps:
            if re.match(r"dependencies\s*=\s*\[", line):
                in_deps = True
                deps += re.findall(r'"([^"]+)"', line.split("[", 1)[1])
            continue
        if line.strip() == "]":
            break
        deps += re.findall(r'"([^"]+)"', line)
    if not deps:
        raise SystemExit("could not find dependencies list in pyproject.toml")
    return {_pkg_name(d) for d in deps}


def main() -> int:
    py_deps = _pyproject_deps((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    req_names = set()
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        req_names.add(_pkg_name(line))

    missing_from_req = sorted(py_deps - req_names)
    missing_from_py = sorted((req_names - py_deps) - TRANSITIVE_DEPS)
    ok = True
    if missing_from_req:
        print(
            "FAIL: in pyproject.toml but missing from requirements.txt: "
            f"{missing_from_req}"
        )
        ok = False
    if missing_from_py:
        print(
            "FAIL: in requirements.txt but missing from pyproject.toml: "
            f"{missing_from_py}"
        )
        print(
            "Add them to pyproject.toml (single source of truth) or to "
            "TRANSITIVE_DEPS in this script if they are transitive pins."
        )
        ok = False
    if ok:
        print(
            f"OK: pyproject.toml and requirements.txt agree on "
            f"{len(py_deps)} direct dependencies."
        )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
